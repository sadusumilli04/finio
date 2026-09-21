import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.constants import (
    SUBSCRIPTION_MIN_CHANGE,
    SUBSCRIPTION_MIN_PCT,
    SUBSCRIPTION_MISSING_GRACE_DAYS,
    SUBSCRIPTION_NEW_MONTHS,
)
from finio.services.insights.windows import Windows, shift_month
from finio.services.recurring import find_recurring

KIND_ORDER = {"missing": 0, "price_up": 1, "price_down": 2, "new": 3}


def _item(merchant: str, kind: str, current: int | None, previous: int | None, expected: date | None = None) -> dict:
    return {
        "merchant": merchant, "kind": kind, "current": current, "previous": previous,
        "expected_date": expected.isoformat() if expected else None,
    }


def _charges(conn: sqlite3.Connection, merchants: set[str]) -> dict[str, list[tuple[date, int]]]:
    where, params = spending_where()
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, t.transaction_date AS d, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE {where} AND {EFFECTIVE_AMOUNT} > 0 ORDER BY t.transaction_date, t.id",
        params,
    )
    grouped: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for r in rows:
        if r["merchant"] in merchants:
            grouped[r["merchant"]].append((date.fromisoformat(r["d"]), r["amount"]))
    return grouped


def build_subscriptions(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    monthly = {hit["merchant"] for hit in find_recurring(conn) if hit["cadence"] == "monthly"}
    if not monthly:
        return []
    new_year, new_month = shift_month(windows.month_start.year, windows.month_start.month, -(SUBSCRIPTION_NEW_MONTHS - 1))
    new_cutoff = date(new_year, new_month, 1)
    deadline = windows.current_end - timedelta(days=SUBSCRIPTION_MISSING_GRACE_DAYS)

    items = []
    for merchant, charges in _charges(conn, monthly).items():
        in_window = [i for i, (when, _) in enumerate(charges) if windows.current_start <= when <= windows.current_end]
        before = [charge for charge in charges if charge[0] < windows.month_start]

        if in_window:
            latest = in_window[-1]
            if latest > 0:
                amount, previous = charges[latest][1], charges[latest - 1][1]
                difference = amount - previous
                if abs(difference) >= max(SUBSCRIPTION_MIN_CHANGE, previous * SUBSCRIPTION_MIN_PCT / 100):
                    items.append(_item(merchant, "price_up" if difference > 0 else "price_down", amount, previous))
        elif len(before) >= 2:
            gaps = [(later[0] - earlier[0]).days for earlier, later in zip(before, before[1:])]
            expected = before[-1][0] + timedelta(days=round(statistics.median(gaps)))
            if windows.current_start <= expected <= deadline:
                items.append(_item(merchant, "missing", None, before[-1][1], expected))

        if new_cutoff <= charges[0][0] <= windows.current_end:
            items.append(_item(merchant, "new", charges[in_window[-1]][1] if in_window else None, None))

    items.sort(key=lambda i: (KIND_ORDER[i["kind"]], i["merchant"]))
    return items
