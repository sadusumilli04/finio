import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.filters import where_clause

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.25
CADENCES = [("weekly", 7, 2), ("biweekly", 14, 3), ("monthly", 30, 5), ("yearly", 365, 10)]


def detect(merchant: str, txns: list[tuple[str, int]]) -> dict | None:
    dates = sorted({date.fromisoformat(d) for d, _ in txns})
    if len(dates) < MIN_OCCURRENCES:
        return None

    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    median_gap = statistics.median(gaps)
    cadence = next(
        (
            name
            for name, center, tol in CADENCES
            if abs(median_gap - center) <= tol and all(abs(g - median_gap) <= tol for g in gaps)
        ),
        None,
    )
    if cadence is None:
        return None

    amounts = [a for _, a in txns]
    typical = int(statistics.median(amounts))
    if typical <= 0 or (max(amounts) - min(amounts)) / typical > AMOUNT_TOLERANCE:
        return None

    last = dates[-1]
    return {
        "merchant": merchant,
        "cadence": cadence,
        "typical_amount": typical,
        "count": len(dates),
        "last_date": last.isoformat(),
        "next_expected": (last + timedelta(days=round(median_gap))).isoformat(),
    }


def find_recurring(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = where_clause(**filters)
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, t.transaction_date AS d, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE t.type = 'purchase' AND {EFFECTIVE_AMOUNT} <> 0 "
        f"AND t.merchant_clean != '' AND {where}",
        params,
    )
    grouped: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in rows:
        grouped[r["merchant"]].append((r["d"], r["amount"]))
    found = [hit for m, txns in grouped.items() if (hit := detect(m, txns))]
    return sorted(found, key=lambda h: (-h["typical_amount"], h["merchant"]))
