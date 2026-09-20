def insert_txn(
    conn,
    account_id,
    *,
    date="2026-09-01",
    amount=1000,
    type="purchase",
    merchant="Shop",
    description=None,
    cardholder=None,
    category="Other",
    origin="import",
    category_source="source_default",
    posted=None,
    source_category=None,
):
    cat_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO transactions(account_id, posted_date, transaction_date, amount, type, "
        "raw_description, merchant_raw, merchant_clean, cardholder, category_id, category_source, origin, source_category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (account_id, posted, date, amount, type, description or merchant, merchant, merchant,
         cardholder, cat_id, category_source, origin, source_category),
    )
    conn.commit()
    return cur.lastrowid
