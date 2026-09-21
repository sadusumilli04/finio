from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()


def make_acct(client, source="apple_card_csv", name="Apple Card", type_="credit_card"):
    r = client.post("/api/accounts", json={"name": name, "type": type_, "source": source})
    assert r.status_code == 201, r.text
    return r.json()


def import_fixture(client, account_id):
    r = client.post("/api/imports", data={"account_id": account_id}, files={"file": ("a.csv", FIXTURE)})
    assert r.status_code == 200, r.text
    return r.json()


def add_manual(client, account_id, merchant="Corner Cafe"):
    other = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Other")
    r = client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-09-10", "amount": 500,
        "direction": "expense", "merchant": merchant, "category_id": other,
    })
    assert r.status_code == 201, r.text


def txn_count(client, **params):
    return client.get("/api/transactions", params=params).json()["total"]


def test_account_list_reports_transaction_count(client):
    apple = make_acct(client)
    empty = make_acct(client, source="manual", name="Empty", type_="checking")
    assert apple["transaction_count"] == 0
    import_fixture(client, apple["id"])
    counts = {a["id"]: a["transaction_count"] for a in client.get("/api/accounts").json()}
    assert counts == {apple["id"]: 6, empty["id"]: 0}


def test_delete_account_removes_its_transactions_and_import_history(client, conn):
    apple = make_acct(client)
    bank = make_acct(client, source="manual", name="Chase", type_="checking")
    import_fixture(client, apple["id"])
    add_manual(client, apple["id"])
    add_manual(client, bank["id"], merchant="Keep Me")
    assert txn_count(client) == 8

    assert client.delete(f"/api/accounts/{apple['id']}").status_code == 204

    assert [a["id"] for a in client.get("/api/accounts").json()] == [bank["id"]]
    assert txn_count(client) == 1
    assert client.get("/api/transactions").json()["items"][0]["merchant"] == "Keep Me"
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (apple["id"],)).fetchone()[0] == 0


def test_delete_leaves_other_accounts_import_history_alone(client, conn):
    first = make_acct(client, name="Card A")
    second = make_acct(client, name="Card B")
    import_fixture(client, first["id"])
    import_fixture(client, second["id"])

    assert client.delete(f"/api/accounts/{first['id']}").status_code == 204

    assert txn_count(client) == 6
    assert txn_count(client, account_id=second["id"]) == 6
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 1


def test_delete_empty_account_and_unknown_account(client):
    empty = make_acct(client, source="manual", name="Empty", type_="checking")
    assert client.delete(f"/api/accounts/{empty['id']}").status_code == 204
    assert client.get("/api/accounts").json() == []
    assert client.delete(f"/api/accounts/{empty['id']}").status_code == 404
    assert client.delete("/api/accounts/9999").status_code == 404


def test_same_file_can_be_imported_again_after_the_account_is_deleted(client):
    apple = make_acct(client)
    import_fixture(client, apple["id"])
    client.delete(f"/api/accounts/{apple['id']}")
    again = make_acct(client)
    assert import_fixture(client, again["id"])["rows_added"] == 6
