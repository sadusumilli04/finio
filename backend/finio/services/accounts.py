import sqlite3

from finio.errors import NotFoundError

ACCOUNT_SELECT = """
SELECT a.*, (SELECT COUNT(*) FROM transactions t WHERE t.account_id = a.id) AS transaction_count
FROM accounts a
"""


def list_accounts(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(ACCOUNT_SELECT + " ORDER BY a.id")]


def get_account(conn: sqlite3.Connection, account_id: int) -> dict:
    row = conn.execute(ACCOUNT_SELECT + " WHERE a.id = ?", (account_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Account {account_id} not found")
    return dict(row)


def delete_account(conn: sqlite3.Connection, account_id: int) -> None:
    """Delete an account together with its transactions and import history, atomically."""
    get_account(conn, account_id)
    with conn:
        conn.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM import_batches WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
