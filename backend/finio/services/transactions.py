import sqlite3

from finio.errors import NotFoundError
from finio.services.filters import where_clause

TXN_SELECT = """
SELECT t.id, t.account_id, a.name AS account_name, t.transaction_date, t.posted_date, t.amount,
       t.type, t.merchant_clean AS merchant, t.raw_description AS description, t.cardholder,
       t.category_id, c.name AS category, t.category_source, t.origin
FROM transactions t
JOIN accounts a ON a.id = t.account_id
JOIN categories c ON c.id = t.category_id
"""

SORT_COLUMNS = {"date": "t.transaction_date", "amount": "t.amount", "merchant": "t.merchant_clean"}


def get_transaction(conn: sqlite3.Connection, transaction_id: int) -> dict:
    row = conn.execute(TXN_SELECT + " WHERE t.id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    return dict(row)


def list_transactions(
    conn: sqlite3.Connection, *, sort: str = "date", order: str = "desc",
    limit: int = 50, offset: int = 0, **filters,
) -> dict:
    where, params = where_clause(**filters)
    direction = "ASC" if order == "asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM transactions t WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"{TXN_SELECT} WHERE {where} ORDER BY {SORT_COLUMNS[sort]} {direction}, t.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total}
