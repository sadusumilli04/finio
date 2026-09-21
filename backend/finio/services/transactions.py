import sqlite3

from finio.errors import ForbiddenError, NotFoundError, ValidationFailed
from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.filters import where_clause
from finio.services.merchants import clean_merchant, load_aliases, normalize_whitespace

TXN_SELECT = f"""
SELECT t.id, t.account_id, a.name AS account_name, t.transaction_date, t.posted_date, t.amount,
       t.type, t.merchant_clean AS merchant, t.raw_description AS description, t.cardholder,
       t.category_id, c.name AS category, t.category_source, t.origin,
       t.my_share, t.share_source, {EFFECTIVE_AMOUNT} AS effective_amount
FROM transactions t
JOIN accounts a ON a.id = t.account_id
JOIN categories c ON c.id = t.category_id
"""

SORT_COLUMNS = {"date": "t.transaction_date", "amount": EFFECTIVE_AMOUNT, "merchant": "t.merchant_clean"}


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


DIRECTION_TO_TYPE = {"expense": "purchase", "income": "income", "refund": "refund"}
TYPE_TO_DIRECTION = {v: k for k, v in DIRECTION_TO_TYPE.items()}


def _signed(direction: str, amount: int) -> int:
    return abs(amount) if direction == "expense" else -abs(amount)


def _require_category(conn: sqlite3.Connection, category_id: int) -> None:
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise ValidationFailed(f"Category {category_id} does not exist")


SHARE_FIELDS = {"category_id", "my_share"}


def _share_columns(row, my_share, source: str = "manual", *, new_type=None, new_amount=None) -> dict:
    """Column updates that set or clear the split, validated against the (possibly just-edited) charge."""
    if my_share is None:
        return {"my_share": None, "share_source": None}
    if source not in {"manual", "venmo"}:
        raise ValidationFailed("Unknown share source")
    type_ = new_type or row["type"]
    charge = abs(new_amount) if new_amount is not None else row["amount"]
    if type_ != "purchase":
        raise ValidationFailed("Only purchases can be split")
    if my_share < 0 or my_share > charge:
        raise ValidationFailed("Your share must be between $0.00 and the charge")
    return {"my_share": my_share, "share_source": source}


def set_share(conn: sqlite3.Connection, transaction_id: int, my_share: int | None, source: str = "manual") -> dict:
    """Set (or clear, with None) how much of a purchase is the user's. Other sources, such as a Venmo importer, call this too."""
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    sets = _share_columns(row, my_share, source)
    with conn:
        conn.execute(
            "UPDATE transactions SET my_share = ?, share_source = ? WHERE id = ?",
            (sets["my_share"], sets["share_source"], transaction_id),
        )
    return get_transaction(conn, transaction_id)


def create_manual(conn: sqlite3.Connection, data: dict) -> dict:
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (data["account_id"],)).fetchone() is None:
        raise NotFoundError(f"Account {data['account_id']} not found")
    _require_category(conn, data["category_id"])
    merchant = normalize_whitespace(data["merchant"])
    date = str(data["date"])
    with conn:
        cur = conn.execute(
            "INSERT INTO transactions(account_id, posted_date, transaction_date, amount, type, "
            "raw_description, merchant_raw, merchant_clean, cardholder, category_id, category_source, origin) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'manual','manual')",
            (data["account_id"], date, date, _signed(data["direction"], data["amount"]),
             DIRECTION_TO_TYPE[data["direction"]], data.get("description") or merchant, merchant,
             clean_merchant(merchant, load_aliases(conn)), data.get("cardholder") or None, data["category_id"]),
        )
    return get_transaction(conn, cur.lastrowid)


def update_transaction(conn: sqlite3.Connection, transaction_id: int, fields: dict) -> dict:
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    if row["origin"] == "import" and set(fields) - SHARE_FIELDS:
        raise ForbiddenError("Imported transactions can only be recategorized or split")
    if "category_id" in fields:
        if fields["category_id"] is None:
            raise ValidationFailed("category_id cannot be null")
        _require_category(conn, fields["category_id"])

    # Reject explicit nulls for non-nullable fields
    for field in ["merchant", "date", "amount", "direction"]:
        if field in fields and fields[field] is None:
            raise ValidationFailed(f"{field} cannot be null")

    sets: dict = {}
    if "category_id" in fields:
        sets["category_id"] = fields["category_id"]
        sets["category_source"] = "manual"
    if row["origin"] == "manual":
        if "merchant" in fields:
            merchant = normalize_whitespace(fields["merchant"])
            sets["merchant_raw"] = merchant
            sets["merchant_clean"] = clean_merchant(merchant, load_aliases(conn))
        if "description" in fields:
            sets["raw_description"] = fields["description"] or sets.get("merchant_raw") or row["merchant_raw"]
        if "date" in fields:
            sets["transaction_date"] = sets["posted_date"] = str(fields["date"])
        if "cardholder" in fields:
            sets["cardholder"] = fields["cardholder"] or None
        if "amount" in fields or "direction" in fields:
            direction = fields.get("direction") or TYPE_TO_DIRECTION.get(row["type"], "expense")
            amount = fields.get("amount", abs(row["amount"]))
            sets["amount"] = _signed(direction, amount)
            sets["type"] = DIRECTION_TO_TYPE[direction]
    if "my_share" in fields:
        sets.update(_share_columns(row, fields["my_share"], new_type=sets.get("type"), new_amount=sets.get("amount")))
    elif row["my_share"] is not None and ("amount" in sets or "type" in sets):
        if sets.get("type", row["type"]) != "purchase":
            sets["my_share"] = None
            sets["share_source"] = None
        elif sets.get("amount", row["amount"]) < row["my_share"]:
            raise ValidationFailed("The split exceeds the new charge; edit the split first")
    if sets:
        assignments = ", ".join(f"{col} = ?" for col in sets)
        with conn:
            conn.execute(f"UPDATE transactions SET {assignments} WHERE id = ?", [*sets.values(), transaction_id])
    return get_transaction(conn, transaction_id)


def delete_transaction(conn: sqlite3.Connection, transaction_id: int) -> None:
    row = conn.execute("SELECT origin FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    if row["origin"] == "import":
        raise ForbiddenError("Imported transactions cannot be deleted")
    with conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
