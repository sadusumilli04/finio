from tests.helpers import insert_txn


def test_category_totals_use_the_share(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, category="Restaurants")
    insert_txn(conn, acct, merchant="Cafe", amount=1000, category="Restaurants")
    data = client.get("/api/analytics/spending-by-category").json()
    assert [(d["category"], d["total"], d["count"]) for d in data] == [("Restaurants", 4000, 2)]


def test_trends_and_merchants_use_the_share(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, date="2026-09-10")
    insert_txn(conn, acct, merchant="Home Plate", amount=8000, date="2026-08-10")
    assert client.get("/api/analytics/trends").json() == [
        {"month": "2026-08", "total": 8000},
        {"month": "2026-09", "total": 3000},
    ]
    assert client.get("/api/analytics/top-merchants").json() == [
        {"merchant": "Home Plate", "total": 11000, "count": 2},
    ]


def test_fully_repaid_purchase_leaves_analytics_but_stays_in_the_list(client, conn, make_account):
    acct = make_account()
    zero = insert_txn(conn, acct, merchant="Birthday Dinner", amount=20000, my_share=0, category="Restaurants")
    insert_txn(conn, acct, merchant="Cafe", amount=1500, category="Grocery")
    cats = client.get("/api/analytics/spending-by-category").json()
    assert [(c["category"], c["total"]) for c in cats] == [("Grocery", 1500)]
    merchants = client.get("/api/analytics/top-merchants").json()
    assert [m["merchant"] for m in merchants] == ["Cafe"]
    assert [t["id"] for t in client.get("/api/transactions", params={"q": "birthday"}).json()["items"]] == [zero]


def test_recurring_uses_the_share(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, merchant="Book Club Dinner", amount=6000, my_share=2000, date=d)
    data = client.get("/api/analytics/recurring").json()
    assert [(r["merchant"], r["typical_amount"], r["cadence"]) for r in data] == [("Book Club Dinner", 2000, "monthly")]


def test_recurring_ignores_fully_repaid_charges(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, merchant="Covered Dinner", amount=6000, my_share=0, date=d)
    assert client.get("/api/analytics/recurring").json() == []
