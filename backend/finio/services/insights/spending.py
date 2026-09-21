import sqlite3
from datetime import date

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where


def window_total(conn: sqlite3.Connection, start: date, end: date) -> int:
    """What the user spent between two dates (inclusive), at their share."""
    where, params = spending_where(date_from=start, date_to=end)
    row = conn.execute(f"SELECT COALESCE(SUM({EFFECTIVE_AMOUNT}), 0) FROM transactions t WHERE {where}", params)
    return row.fetchone()[0]


def monthly_totals(conn: sqlite3.Connection) -> dict[str, int]:
    """Total spending per calendar month ("YYYY-MM"), months with spending only, oldest first."""
    where, params = spending_where()
    rows = conn.execute(
        f"SELECT strftime('%Y-%m', t.transaction_date) AS month, SUM({EFFECTIVE_AMOUNT}) AS total "
        f"FROM transactions t WHERE {where} GROUP BY month ORDER BY month",
        params,
    )
    return {r["month"]: r["total"] for r in rows}
