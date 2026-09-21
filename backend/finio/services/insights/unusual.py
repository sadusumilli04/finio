import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.common import median_cents
from finio.services.insights.constants import (
    UNUSUAL_LIMIT,
    UNUSUAL_MIN_AMOUNT,
    UNUSUAL_MIN_HISTORY,
    UNUSUAL_RATIO,
)
from finio.services.insights.windows import Windows


def _category_history(conn: sqlite3.Connection, before: date) -> dict[int, list[int]]:
    where, params = spending_where(date_to=before - timedelta(days=1))
    history: dict[int, list[int]] = defaultdict(list)
    rows = conn.execute(
        f"SELECT t.category_id AS category_id, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE {where} AND {EFFECTIVE_AMOUNT} > 0",
        params,
    )
    for r in rows:
        history[r["category_id"]].append(r["amount"])
    return history


def build_unusual(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    history = _category_history(conn, windows.month_start)
    where, params = spending_where(date_from=windows.current_start, date_to=windows.current_end)
    rows = conn.execute(
        f"SELECT t.id AS transaction_id, t.transaction_date AS date, COALESCE(NULLIF(t.merchant_clean, ''), t.raw_description) AS merchant, "
        f"t.category_id AS category_id, c.name AS category, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id "
        f"WHERE {where} AND {EFFECTIVE_AMOUNT} > 0",
        params,
    )
    items = []
    for r in rows:
        earlier = history.get(r["category_id"], [])
        if len(earlier) < UNUSUAL_MIN_HISTORY:
            continue
        typical = median_cents(earlier)
        if r["amount"] >= UNUSUAL_RATIO * typical and r["amount"] >= UNUSUAL_MIN_AMOUNT:
            items.append({
                "transaction_id": r["transaction_id"], "date": r["date"], "merchant": r["merchant"],
                "category": r["category"], "amount": r["amount"], "typical": typical,
            })
    items.sort(key=lambda i: (-i["amount"], i["date"], i["transaction_id"]))
    return items[:UNUSUAL_LIMIT]
