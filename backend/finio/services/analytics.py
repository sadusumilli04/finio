import sqlite3

from finio.services.filters import where_clause


def _spending_where(**filters) -> tuple[str, list]:
    where, params = where_clause(**filters)
    return f"t.type = 'purchase' AND {where}", params


def spending_by_category(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT c.id AS category_id, c.name AS category, SUM(t.amount) AS total, COUNT(*) AS count "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id WHERE {where} "
        "GROUP BY c.id ORDER BY total DESC, c.name",
        params,
    )
    return [dict(r) for r in rows]


def spending_trends(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT strftime('%Y-%m', t.transaction_date) AS month, SUM(t.amount) AS total "
        f"FROM transactions t WHERE {where} GROUP BY month ORDER BY month",
        params,
    )
    return [dict(r) for r in rows]


def top_merchants(conn: sqlite3.Connection, limit: int = 10, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT t.merchant_clean AS merchant, SUM(t.amount) AS total, COUNT(*) AS count "
        f"FROM transactions t WHERE {where} AND t.merchant_clean != '' "
        "GROUP BY t.merchant_clean ORDER BY total DESC, merchant LIMIT ?",
        [*params, limit],
    )
    return [dict(r) for r in rows]
