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
    from finio.services.venmo_links import recalculate_share

    get_account(conn, account_id)
    with conn:
        affected = [
            r["id"] for r in conn.execute(
                "SELECT DISTINCT l.card_transaction_id AS id FROM venmo_links l "
                "JOIN transactions v ON v.id = l.venmo_transaction_id "
                "JOIN transactions c ON c.id = l.card_transaction_id "
                "WHERE v.account_id = ? OR c.account_id = ?",
                (account_id, account_id),
            )
        ]
        conn.execute(
            "DELETE FROM venmo_links WHERE venmo_transaction_id IN "
            "(SELECT id FROM transactions WHERE account_id = ?) "
            "OR card_transaction_id IN (SELECT id FROM transactions WHERE account_id = ?)",
            (account_id, account_id),
        )
        conn.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM import_batches WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        for charge_id in affected:
            if conn.execute("SELECT 1 FROM transactions WHERE id = ?", (charge_id,)).fetchone():
                recalculate_share(conn, charge_id)
