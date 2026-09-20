from tests.helpers import insert_txn


def cat(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def rule_body(client, **over):
    body = dict(match_field="merchant", match_type="contains", pattern="target", category_id=cat(client, "Grocery"))
    body.update(over)
    return body


def test_rule_crud(client):
    r = client.post("/api/rules", json=rule_body(client))
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["priority"] == 100
    assert client.get("/api/rules").json() == [rule]
    patched = client.patch(f"/api/rules/{rule['id']}", json={"pattern": "target store", "priority": 5}).json()
    assert (patched["pattern"], patched["priority"]) == ("target store", 5)
    assert client.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert client.get("/api/rules").json() == []


def test_rule_validation(client):
    assert client.post("/api/rules", json=rule_body(client, pattern="  ")).status_code == 422
    assert client.post("/api/rules", json=rule_body(client, match_field="amount")).status_code == 422
    assert client.post("/api/rules", json=rule_body(client, category_id=9999)).status_code == 400
    assert client.patch("/api/rules/999", json={"pattern": "x"}).status_code == 404
    assert client.delete("/api/rules/999").status_code == 404


def test_reapply(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Target Store", category="Other")
    client.post("/api/rules", json=rule_body(client))
    assert client.post("/api/rules/reapply").json() == {"updated": 1}
    assert client.get("/api/transactions").json()["items"][0]["category"] == "Grocery"
    assert client.post("/api/rules/reapply").json() == {"updated": 0}


def test_alias_crud(client):
    r = client.post("/api/aliases", json={"pattern": "sq *", "clean_name": "Square Vendor"})
    assert r.status_code == 201
    alias = r.json()
    assert client.get("/api/aliases").json() == [alias]
    assert client.post("/api/aliases", json={"pattern": " ", "clean_name": "X"}).status_code == 422
    assert client.delete(f"/api/aliases/{alias['id']}").status_code == 204
    assert client.delete(f"/api/aliases/{alias['id']}").status_code == 404
