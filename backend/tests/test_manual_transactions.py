from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()


def cat(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def manual_account(client):
    return client.post("/api/accounts", json={"name": "Chase", "type": "checking", "source": "manual"}).json()["id"]


def create(client, acct, **over):
    body = dict(account_id=acct, date="2026-09-10", amount=4250, direction="expense",
                merchant="  Corner   Cafe ", category_id=cat(client, "Restaurants"))
    body.update(over)
    return client.post("/api/transactions", json=body)


def test_create_expense(client):
    acct = manual_account(client)
    r = create(client, acct, description="Lunch", cardholder="Ann")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["amount"] == 4250 and t["type"] == "purchase"
    assert t["merchant"] == "Corner Cafe" and t["description"] == "Lunch"
    assert t["origin"] == "manual" and t["category_source"] == "manual" and t["category"] == "Restaurants"
    assert t["transaction_date"] == "2026-09-10" and t["cardholder"] == "Ann"


def test_income_and_refund_are_negative(client):
    acct = manual_account(client)
    inc = create(client, acct, direction="income", merchant="Employer", category_id=cat(client, "Other")).json()
    ref = create(client, acct, direction="refund").json()
    assert (inc["amount"], inc["type"]) == (-4250, "income")
    assert (ref["amount"], ref["type"]) == (-4250, "refund")


def test_description_defaults_to_merchant(client):
    acct = manual_account(client)
    assert create(client, acct).json()["description"] == "Corner Cafe"


def test_alias_applied_to_manual_merchant(client, conn):
    acct = manual_account(client)
    conn.execute("INSERT INTO merchant_aliases(pattern, clean_name) VALUES ('corner cafe', 'Corner Café')")
    conn.commit()
    assert create(client, acct).json()["merchant"] == "Corner Café"


def test_create_validation(client):
    acct = manual_account(client)
    assert create(client, acct, amount=0).status_code == 422
    assert create(client, acct, amount=-5).status_code == 422
    assert create(client, acct, merchant="   ").status_code == 422
    assert create(client, acct, date="not-a-date").status_code == 422
    assert create(client, acct, direction="gift").status_code == 422
    assert create(client, 999).status_code == 404
    assert create(client, acct, category_id=9999).status_code == 400


def test_edit_manual_fields(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    r = client.patch(f"/api/transactions/{tid}", json={
        "amount": 1000, "merchant": "New Place", "date": "2026-09-11",
        "description": "Edited", "cardholder": "Bob", "category_id": cat(client, "Shopping"),
    })
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["amount"], t["merchant"], t["transaction_date"]) == (1000, "New Place", "2026-09-11")
    assert (t["description"], t["cardholder"], t["category"]) == ("Edited", "Bob", "Shopping")


def test_edit_direction_alone_flips_sign_and_amount_alone_keeps_sign(client):
    acct = manual_account(client)
    tid = create(client, acct, direction="income").json()["id"]
    t = client.patch(f"/api/transactions/{tid}", json={"amount": 999}).json()
    assert (t["amount"], t["type"]) == (-999, "income")
    t = client.patch(f"/api/transactions/{tid}", json={"direction": "expense"}).json()
    assert (t["amount"], t["type"]) == (999, "purchase")


def test_edit_validation(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    assert client.patch(f"/api/transactions/{tid}", json={"amount": 0}).status_code == 422
    assert client.patch(f"/api/transactions/{tid}", json={"category_id": 9999}).status_code == 400
    assert client.patch("/api/transactions/9999", json={"merchant": "X"}).status_code == 404


def test_imported_rows_only_recategorizable_and_not_deletable(client):
    apple = client.post("/api/accounts", json={"name": "Apple", "type": "credit_card", "source": "apple_card_csv"}).json()
    client.post("/api/imports", data={"account_id": apple["id"]}, files={"file": ("a.csv", FIXTURE)})
    row = client.get("/api/transactions", params={"merchant": "target"}).json()["items"][0]
    assert client.patch(f"/api/transactions/{row['id']}", json={"amount": 1}).status_code == 403
    assert client.patch(f"/api/transactions/{row['id']}", json={"merchant": "X"}).status_code == 403
    ok = client.patch(f"/api/transactions/{row['id']}", json={"category_id": cat(client, "Shopping")})
    assert ok.status_code == 200
    assert ok.json()["category"] == "Shopping" and ok.json()["category_source"] == "manual"
    assert client.delete(f"/api/transactions/{row['id']}").status_code == 403


def test_delete_manual(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    assert client.delete(f"/api/transactions/{tid}").status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.delete(f"/api/transactions/{tid}").status_code == 404


def test_manual_category_survives_rule_reapply(client, conn):
    from finio.services.rules import reapply_rules

    acct = manual_account(client)
    tid = create(client, acct, merchant="Target Run", category_id=cat(client, "Shopping")).json()["id"]
    conn.execute(
        "INSERT INTO category_rules(match_field, match_type, pattern, category_id) VALUES ('merchant','contains','target',?)",
        (cat(client, "Grocery"),),
    )
    conn.commit()
    reapply_rules(conn)
    assert client.get("/api/transactions").json()["items"][0]["category"] == "Shopping"


def test_explicit_null_rejected_for_non_nullable_fields(client):
    acct = manual_account(client)
    tid = create(client, acct, description="Lunch", cardholder="Ann").json()["id"]
    original = client.get(f"/api/transactions/{tid}").json()

    # Test date null -> 400
    r = client.patch(f"/api/transactions/{tid}", json={"date": None})
    assert r.status_code == 400, r.text
    assert client.get(f"/api/transactions/{tid}").json() == original

    # Test amount null -> 400
    r = client.patch(f"/api/transactions/{tid}", json={"amount": None})
    assert r.status_code == 400, r.text
    assert client.get(f"/api/transactions/{tid}").json() == original

    # Test merchant null -> 400
    r = client.patch(f"/api/transactions/{tid}", json={"merchant": None})
    assert r.status_code == 400, r.text
    assert client.get(f"/api/transactions/{tid}").json() == original

    # Test direction null -> 400
    r = client.patch(f"/api/transactions/{tid}", json={"direction": None})
    assert r.status_code == 400, r.text
    assert client.get(f"/api/transactions/{tid}").json() == original


def test_explicit_null_clears_nullable_fields(client):
    acct = manual_account(client)
    tid = create(client, acct, description="Lunch", cardholder="Ann").json()["id"]

    # Clear description with null
    r = client.patch(f"/api/transactions/{tid}", json={"description": None})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["description"] == "Corner Cafe"  # Falls back to merchant

    # Clear cardholder with null
    r = client.patch(f"/api/transactions/{tid}", json={"cardholder": None})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["cardholder"] is None
