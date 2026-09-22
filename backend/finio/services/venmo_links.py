import datetime as dt
import sqlite3

from finio.errors import ConflictError, NotFoundError, ValidationFailed

CANDIDATE_DAYS_BEFORE = 3
CANDIDATE_DAYS_AFTER = 30

_ITEM_SELECT = (
    "SELECT t.id, t.transaction_date AS date, t.merchant_clean AS merchant, "
    "t.raw_description AS description, ABS(t.amount) AS amount FROM transactions t "
)


def _require_charge(conn: sqlite3.Connection, charge_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT t.*, a.source AS account_source FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id WHERE t.id = ?",
        (charge_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {charge_id} not found")
    if row["type"] != "purchase" or row["account_source"] == "venmo_csv":
        raise ValidationFailed("Only a purchase on a non-Venmo account can be linked")
    return row


def _require_payment(conn: sqlite3.Connection, payment_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT t.*, a.source AS account_source FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id WHERE t.id = ?",
        (payment_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {payment_id} not found")
    if row["type"] != "payment" or row["account_source"] != "venmo_csv":
        raise ValidationFailed("Only an incoming Venmo payment can be linked")
    return row


def _linked_total(conn: sqlite3.Connection, charge_id: int) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM venmo_links l "
        "JOIN transactions t ON t.id = l.venmo_transaction_id WHERE l.card_transaction_id = ?",
        (charge_id,),
    ).fetchone()[0]


def is_linked(conn: sqlite3.Connection, charge_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM venmo_links WHERE card_transaction_id = ? LIMIT 1", (charge_id,)
    ).fetchone() is not None


def recalculate_share(conn: sqlite3.Connection, charge_id: int) -> None:
    """Set my_share/share_source from the linked payments. Writes columns directly (not via set_share)."""
    total = _linked_total(conn, charge_id)
    row = conn.execute("SELECT amount, share_source FROM transactions WHERE id = ?", (charge_id,)).fetchone()
    if total == 0:
        if row["share_source"] == "venmo":
            conn.execute(
                "UPDATE transactions SET my_share = NULL, share_source = NULL WHERE id = ?", (charge_id,)
            )
    else:
        conn.execute(
            "UPDATE transactions SET my_share = ?, share_source = 'venmo' WHERE id = ?",
            (row["amount"] - total, charge_id),
        )


def list_candidates(conn: sqlite3.Connection, charge_id: int) -> list[dict]:
    charge = _require_charge(conn, charge_id)
    charge_date = dt.date.fromisoformat(charge["transaction_date"])
    low = (charge_date - dt.timedelta(days=CANDIDATE_DAYS_BEFORE)).isoformat()
    high = (charge_date + dt.timedelta(days=CANDIDATE_DAYS_AFTER)).isoformat()
    rows = conn.execute(
        _ITEM_SELECT + "JOIN accounts a ON a.id = t.account_id "
        "WHERE a.source = 'venmo_csv' AND t.type = 'payment' "
        "AND t.transaction_date BETWEEN ? AND ? "
        "AND t.id NOT IN (SELECT venmo_transaction_id FROM venmo_links)",
        (low, high),
    ).fetchall()
    items = [dict(r) for r in rows]
    items.sort(key=lambda x: (
        abs((dt.date.fromisoformat(x["date"]) - charge_date).days), -x["amount"], x["id"],
    ))
    return items


def list_links(conn: sqlite3.Connection, charge_id: int) -> list[dict]:
    _require_charge(conn, charge_id)
    rows = conn.execute(
        _ITEM_SELECT + "JOIN venmo_links l ON l.venmo_transaction_id = t.id "
        "WHERE l.card_transaction_id = ? ORDER BY t.transaction_date ASC, t.id ASC",
        (charge_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def link_payment(conn: sqlite3.Connection, charge_id: int, venmo_transaction_id: int) -> dict:
    from finio.services.transactions import get_transaction

    charge = _require_charge(conn, charge_id)
    payment = _require_payment(conn, venmo_transaction_id)
    already = conn.execute(
        "SELECT 1 FROM venmo_links WHERE venmo_transaction_id = ?", (venmo_transaction_id,)
    ).fetchone()
    if already is not None:
        raise ConflictError("This Venmo payment is already linked")
    total = _linked_total(conn, charge_id)
    if total + abs(payment["amount"]) > charge["amount"]:
        raise ValidationFailed("The linked payments would exceed the charge")
    with conn:
        conn.execute(
            "INSERT INTO venmo_links(venmo_transaction_id, card_transaction_id) VALUES (?, ?)",
            (venmo_transaction_id, charge_id),
        )
        recalculate_share(conn, charge_id)
    return get_transaction(conn, charge_id)


def unlink_payment(conn: sqlite3.Connection, charge_id: int, venmo_transaction_id: int) -> dict:
    from finio.services.transactions import get_transaction

    row = conn.execute(
        "SELECT 1 FROM venmo_links WHERE venmo_transaction_id = ? AND card_transaction_id = ?",
        (venmo_transaction_id, charge_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Venmo payment {venmo_transaction_id} is not linked to transaction {charge_id}")
    with conn:
        conn.execute("DELETE FROM venmo_links WHERE venmo_transaction_id = ?", (venmo_transaction_id,))
        recalculate_share(conn, charge_id)
    return get_transaction(conn, charge_id)
