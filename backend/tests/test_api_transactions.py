from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    other = make_account(source="manual", name="Bank", type="checking")
    ids = {
        "a": insert_txn(conn, acct, date="2026-09-01", amount=1000, merchant="Target", category="Grocery", cardholder="Ann"),
        "b": insert_txn(conn, acct, date="2026-09-05", amount=2500, merchant="Netflix", category="Entertainment", cardholder="Bob"),
        "c": insert_txn(conn, acct, date="2026-09-10", amount=-5000, type="payment", merchant="Payment", cardholder="Ann"),
        "d": insert_txn(conn, other, date="2026-08-20", amount=700, merchant="Corner Cafe", category="Restaurants",
                        description="CORNER CAFE SF", origin="manual", category_source="manual"),
    }
    return acct, other, ids


def get(client, **params):
    r = client.get("/api/transactions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_shape_and_default_sort(client, conn, make_account):
    _, _, ids = seed(conn, make_account)
    body = get(client)
    assert body["total"] == 4
    assert [t["id"] for t in body["items"]] == [ids["c"], ids["b"], ids["a"], ids["d"]]
    first = body["items"][0]
    assert first["merchant"] == "Payment" and first["category"] == "Other" and first["account_name"] == "Test Card"


def test_filters(client, conn, make_account):
    acct, other, ids = seed(conn, make_account)
    assert {t["id"] for t in get(client, date_from="2026-09-01", date_to="2026-09-05")["items"]} == {ids["a"], ids["b"]}
    assert [t["id"] for t in get(client, account_id=other)["items"]] == [ids["d"]]
    assert {t["id"] for t in get(client, cardholder="Ann")["items"]} == {ids["a"], ids["c"]}
    assert [t["id"] for t in get(client, merchant="netf")["items"]] == [ids["b"]]
    assert [t["id"] for t in get(client, q="corner cafe sf")["items"]] == [ids["d"]]
    assert {t["id"] for t in get(client, min_amount=1000, max_amount=2500)["items"]} == {ids["a"], ids["b"]}
    grocery = client.get("/api/categories").json()
    gid = next(c["id"] for c in grocery if c["name"] == "Grocery")
    assert [t["id"] for t in get(client, category_id=gid)["items"]] == [ids["a"]]


def test_sort_and_paging(client, conn, make_account):
    _, _, ids = seed(conn, make_account)
    by_amount = get(client, sort="amount", order="asc")
    assert [t["id"] for t in by_amount["items"]][0] == ids["c"]
    page = get(client, sort="date", order="asc", limit=2, offset=1)
    assert page["total"] == 4 and [t["id"] for t in page["items"]] == [ids["a"], ids["b"]]


def test_invalid_sort_rejected(client):
    assert client.get("/api/transactions", params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/transactions", params={"limit": 0}).status_code == 422


def test_cardholders_and_merchants(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/cardholders").json() == ["Ann", "Bob"]
    assert client.get("/api/merchants").json() == ["Corner Cafe", "Netflix", "Payment", "Target"]
