from tests.helpers import insert_txn


def seed(conn, make_account):
    card = make_account()
    venmo = make_account(source="venmo_csv", name="Venmo", type="other")
    c = insert_txn(conn, card, date="2026-09-10", amount=18000, merchant="Dinner Place", category="Restaurants")
    p = insert_txn(conn, venmo, date="2026-09-11", amount=-4500, type="payment", merchant="Person One",
                   description="dinner")
    return card, venmo, c, p


def test_candidates_shape(client, conn, make_account):
    _, _, c, p = seed(conn, make_account)
    r = client.get(f"/api/transactions/{c}/venmo-candidates")
    assert r.status_code == 200
    assert r.json() == [{"id": p, "date": "2026-09-11", "merchant": "Person One",
                         "description": "dinner", "amount": 4500}]


def test_link_list_unlink_flow(client, conn, make_account):
    _, _, c, p = seed(conn, make_account)
    r = client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": p})
    assert r.status_code == 200
    body = r.json()
    assert (body["id"], body["my_share"], body["share_source"], body["venmo_link_count"]) == (c, 13500, "venmo", 1)

    links = client.get(f"/api/transactions/{c}/venmo-links").json()
    assert [x["id"] for x in links] == [p]
    assert set(links[0]) == {"id", "date", "merchant", "description", "amount"}

    items = {i["id"]: i for i in client.get("/api/transactions").json()["items"]}
    assert items[c]["venmo_link_count"] == 1 and items[c]["venmo_linked_to"] is None
    assert items[p]["venmo_linked_to"] == c and items[p]["venmo_link_count"] == 0

    r = client.delete(f"/api/transactions/{c}/venmo-links/{p}")
    assert r.status_code == 200
    assert r.json()["my_share"] is None and r.json()["venmo_link_count"] == 0


def test_error_statuses(client, conn, make_account):
    card, venmo, c, p = seed(conn, make_account)
    assert client.get("/api/transactions/9999/venmo-candidates").status_code == 404
    assert client.get("/api/transactions/9999/venmo-links").status_code == 404
    assert client.post("/api/transactions/9999/venmo-links", json={"venmo_transaction_id": p}).status_code == 404
    assert client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": 9999}).status_code == 404
    assert client.delete(f"/api/transactions/{c}/venmo-links/{p}").status_code == 404

    r = client.post(f"/api/transactions/{p}/venmo-links", json={"venmo_transaction_id": p})
    assert r.status_code == 400
    assert "Only a purchase on a non-Venmo account" in r.json()["detail"]

    client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": p})
    c2 = insert_txn(conn, card, amount=9000)
    r = client.post(f"/api/transactions/{c2}/venmo-links", json={"venmo_transaction_id": p})
    assert r.status_code == 409
    assert "already linked" in r.json()["detail"]

    big = insert_txn(conn, venmo, date="2026-09-11", amount=-20000, type="payment")
    r = client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": big})
    assert r.status_code == 400
    assert "would exceed the charge" in r.json()["detail"]


def test_patch_share_refused_while_linked(client, conn, make_account):
    _, _, c, p = seed(conn, make_account)
    client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": p})
    r = client.patch(f"/api/transactions/{c}", json={"my_share": 100})
    assert r.status_code == 400
    assert "Unlink the Venmo payments first" in r.json()["detail"]


def test_patch_resending_unchanged_amount_direction_while_linked_succeeds(client, conn, make_account):
    """Regression: the edit form always resends amount/direction on every save. Editing an unrelated
    field on a linked, manually-entered charge must succeed as long as amount/direction don't change."""
    card = make_account()
    venmo = make_account(source="venmo_csv", name="Venmo", type="other")
    c = insert_txn(conn, card, date="2026-09-10", amount=18000, merchant="Dinner Place",
                   category="Restaurants", origin="manual")
    p = insert_txn(conn, venmo, date="2026-09-11", amount=-4500, type="payment", merchant="Person One",
                   description="dinner")
    client.post(f"/api/transactions/{c}/venmo-links", json={"venmo_transaction_id": p})
    cat = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]

    r = client.patch(f"/api/transactions/{c}", json={"amount": 18000, "direction": "expense", "category_id": cat})
    assert r.status_code == 200
    assert r.json()["category"] == "Shopping"
    assert r.json()["my_share"] == 13500

    r = client.patch(f"/api/transactions/{c}", json={"amount": 20000, "direction": "expense"})
    assert r.status_code == 400
    assert "Unlink the Venmo payments first" in r.json()["detail"]
