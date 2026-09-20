from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()


def make_acct(client, source="apple_card_csv", name="Apple Card", type_="credit_card"):
    r = client.post("/api/accounts", json={"name": name, "type": type_, "source": source})
    assert r.status_code == 201, r.text
    return r.json()


def test_accounts_create_and_list(client):
    made = make_acct(client)
    assert made["starting_balance"] == 0
    assert client.get("/api/accounts").json() == [made]


def test_account_validation(client):
    r = client.post("/api/accounts", json={"name": "X", "type": "bogus", "source": "manual"})
    assert r.status_code == 422


def test_categories_seeded_and_crud(client):
    cats = client.get("/api/categories").json()
    assert "Grocery" in [c["name"] for c in cats]
    created = client.post("/api/categories", json={"name": "Pets"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert client.patch(f"/api/categories/{cid}", json={"name": "Pet Care"}).json()["name"] == "Pet Care"
    assert client.post("/api/categories", json={"name": "Pet Care"}).status_code == 409
    assert client.delete(f"/api/categories/{cid}").status_code == 204


def test_cannot_delete_other_or_in_use_category(client):
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    assert client.delete(f"/api/categories/{cats['Other']}").status_code == 409
    acct = make_acct(client)
    client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert client.delete(f"/api/categories/{cats['Grocery']}").status_code == 409


def test_import_endpoint_and_error_mapping(client):
    acct = make_acct(client)
    r = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert r.status_code == 200
    body = r.json()
    assert (body["rows_added"], body["rows_skipped"], body["errors"]) == (6, 0, [])
    dup = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert dup.status_code == 409
    missing = client.post("/api/imports", data={"account_id": 999}, files={"file": ("a.csv", FIXTURE)})
    assert missing.status_code == 404
    manual = make_acct(client, source="manual", name="Bank", type_="checking")
    no_importer = client.post("/api/imports", data={"account_id": manual["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert no_importer.status_code == 400
