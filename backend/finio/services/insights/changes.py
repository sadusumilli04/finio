import sqlite3
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.constants import (
    GROWING_LIMIT,
    GROWING_MIN_CHANGE,
    GROWING_MIN_RATIO,
    MOVER_MIN_CHANGE,
    MOVERS_PER_SIDE,
    NEW_MERCHANTS_LIMIT,
)
from finio.services.insights.windows import Windows


def category_totals(conn: sqlite3.Connection, start: date, end: date) -> dict[int, dict]:
    where, params = spending_where(date_from=start, date_to=end)
    rows = conn.execute(
        f"SELECT c.id AS category_id, c.name AS category, SUM({EFFECTIVE_AMOUNT}) AS total "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id WHERE {where} GROUP BY c.id",
        params,
    )
    return {r["category_id"]: {"category": r["category"], "total": r["total"]} for r in rows}


def merchant_totals(conn: sqlite3.Connection, start: date, end: date) -> dict[str, dict]:
    where, params = spending_where(date_from=start, date_to=end)
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, SUM({EFFECTIVE_AMOUNT}) AS total, COUNT(*) AS count "
        f"FROM transactions t WHERE {where} AND t.merchant_clean != '' GROUP BY t.merchant_clean",
        params,
    )
    return {r["merchant"]: {"total": r["total"], "count": r["count"]} for r in rows}


def _percent(change: int, previous: int) -> float | None:
    return None if previous == 0 else round(change / previous * 100, 1)


def build_movers(current: dict[int, dict], previous: dict[int, dict]) -> dict:
    items = []
    for category_id in current.keys() | previous.keys():
        now, before = current.get(category_id), previous.get(category_id)
        name = (now or before)["category"]
        current_total = now["total"] if now else 0
        previous_total = before["total"] if before else 0
        change = current_total - previous_total
        if abs(change) < MOVER_MIN_CHANGE:
            continue
        items.append({
            "category": name, "category_id": category_id, "current": current_total,
            "previous": previous_total, "change": change, "change_pct": _percent(change, previous_total),
        })
    up = sorted((i for i in items if i["change"] > 0), key=lambda i: (-i["change"], i["category"]))
    down = sorted((i for i in items if i["change"] < 0), key=lambda i: (i["change"], i["category"]))
    return {"up": up[:MOVERS_PER_SIDE], "down": down[:MOVERS_PER_SIDE]}


def build_growing(current: dict[str, dict], previous: dict[str, dict]) -> list[dict]:
    items = []
    for merchant, now in current.items():
        before = previous.get(merchant)
        if not before or before["total"] <= 0:
            continue
        change = now["total"] - before["total"]
        if change >= GROWING_MIN_CHANGE and now["total"] >= GROWING_MIN_RATIO * before["total"]:
            items.append({
                "merchant": merchant, "current": now["total"], "previous": before["total"],
                "change": change, "change_pct": _percent(change, before["total"]),
            })
    items.sort(key=lambda i: (-i["change"], i["merchant"]))
    return items[:GROWING_LIMIT]


def build_new_merchants(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    where, params = spending_where(date_to=windows.month_start - timedelta(days=1))
    if conn.execute(f"SELECT 1 FROM transactions t WHERE {where} LIMIT 1", params).fetchone() is None:
        return []   # no earlier data at all: everything would look new
    earlier = {
        r["merchant"]
        for r in conn.execute(f"SELECT DISTINCT t.merchant_clean AS merchant FROM transactions t WHERE {where}", params)
    }
    current = merchant_totals(conn, windows.current_start, windows.current_end)
    items = [
        {"merchant": merchant, "total": data["total"], "count": data["count"]}
        for merchant, data in current.items()
        if merchant not in earlier
    ]
    items.sort(key=lambda i: (-i["total"], i["merchant"]))
    return items[:NEW_MERCHANTS_LIMIT]
