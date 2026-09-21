from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    for _ in range(3):
        insert_txn(conn, acct, merchant="Alpha", amount=1000, category="Grocery")       # 3000 over 3 visits
    insert_txn(conn, acct, merchant="Bravo", amount=5000, category="Restaurants")       # 5000 over 1 visit
    for _ in range(2):
        insert_txn(conn, acct, merchant="Charlie", amount=1500, category="Grocery")     # 3000 over 2 visits
    insert_txn(conn, acct, merchant="Delta", amount=100, category="Grocery")            # 100 over 1 visit


def merchants(client, **params):
    r = client.get("/api/analytics/top-merchants", params=params)
    assert r.status_code == 200, r.text
    return [m["merchant"] for m in r.json()]


def test_default_and_spent_rank_by_total_then_name(client, conn, make_account):
    seed(conn, make_account)
    assert merchants(client) == ["Bravo", "Alpha", "Charlie", "Delta"]   # Alpha/Charlie tie at 3000: name order
    assert merchants(client, sort="spent") == ["Bravo", "Alpha", "Charlie", "Delta"]


def test_visits_ranks_by_transaction_count_then_total(client, conn, make_account):
    seed(conn, make_account)
    # 3 visits, 2 visits, then the two single visits ordered by total (Bravo 5000 before Delta 100)
    assert merchants(client, sort="visits") == ["Alpha", "Charlie", "Bravo", "Delta"]


def test_limit_applies_after_ranking(client, conn, make_account):
    seed(conn, make_account)
    assert merchants(client, sort="visits", limit=2) == ["Alpha", "Charlie"]
    assert merchants(client, sort="spent", limit=1) == ["Bravo"]


def test_response_shape_is_unchanged(client, conn, make_account):
    seed(conn, make_account)
    top = client.get("/api/analytics/top-merchants", params={"sort": "visits", "limit": 1}).json()
    assert top == [{"merchant": "Alpha", "total": 3000, "count": 3}]


def test_unknown_sort_is_rejected(client):
    assert client.get("/api/analytics/top-merchants", params={"sort": "bogus"}).status_code == 422


def test_category_filter_narrows_merchants(client, conn, make_account):
    seed(conn, make_account)
    restaurants = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Restaurants")
    assert merchants(client, category_id=restaurants) == ["Bravo"]
    assert merchants(client, category_id=restaurants, sort="visits") == ["Bravo"]
