from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=1000, merchant="Target", category="Grocery", cardholder="Ann")
    insert_txn(conn, acct, date="2026-09-02", amount=2000, merchant="Target", category="Grocery", cardholder="Bob")
    insert_txn(conn, acct, date="2026-09-03", amount=500, merchant="Netflix", category="Entertainment", cardholder="Ann")
    insert_txn(conn, acct, date="2026-09-04", amount=-9999, type="payment", merchant="Payment", category="Other")
    insert_txn(conn, acct, date="2026-09-05", amount=-300, type="refund", merchant="Target", category="Grocery")
    return acct


def test_spending_by_category_excludes_payments_and_refunds(client, conn, make_account):
    seed(conn, make_account)
    data = client.get("/api/analytics/spending-by-category").json()
    assert data == [
        {"category_id": data[0]["category_id"], "category": "Grocery", "total": 3000, "count": 2},
        {"category_id": data[1]["category_id"], "category": "Entertainment", "total": 500, "count": 1},
    ]


def test_filters_apply(client, conn, make_account):
    seed(conn, make_account)
    data = client.get("/api/analytics/spending-by-category", params={"cardholder": "Ann"}).json()
    assert {(d["category"], d["total"]) for d in data} == {("Grocery", 1000), ("Entertainment", 500)}
    data = client.get("/api/analytics/spending-by-category", params={"date_from": "2026-09-01"}).json()
    assert {(d["category"], d["total"]) for d in data} == {("Grocery", 2000), ("Entertainment", 500)}


def test_trends_by_month(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/analytics/trends").json() == [
        {"month": "2026-08", "total": 1000},
        {"month": "2026-09", "total": 2500},
    ]


def test_trends_for_one_category(client, conn, make_account):
    seed(conn, make_account)
    grocery = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Grocery")
    data = client.get("/api/analytics/trends", params={"category_id": grocery}).json()
    assert data == [{"month": "2026-08", "total": 1000}, {"month": "2026-09", "total": 2000}]


def test_top_merchants(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/analytics/top-merchants").json() == [
        {"merchant": "Target", "total": 3000, "count": 2},
        {"merchant": "Netflix", "total": 500, "count": 1},
    ]
    one = client.get("/api/analytics/top-merchants", params={"limit": 1}).json()
    assert len(one) == 1 and one[0]["merchant"] == "Target"
    assert client.get("/api/analytics/top-merchants", params={"limit": 0}).status_code == 422


def test_empty_database(client):
    assert client.get("/api/analytics/spending-by-category").json() == []
    assert client.get("/api/analytics/trends").json() == []
    assert client.get("/api/analytics/top-merchants").json() == []


def test_manual_rows_count_in_spending(client, conn, make_account):
    acct = make_account(source="manual", type="checking")
    insert_txn(conn, acct, amount=4200, merchant="Cafe", category="Restaurants",
               origin="manual", category_source="manual")
    data = client.get("/api/analytics/spending-by-category").json()
    assert [(d["category"], d["total"]) for d in data] == [("Restaurants", 4200)]
