from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    split = insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, date="2026-09-10")
    plain = insert_txn(conn, acct, merchant="Target", amount=5000, date="2026-09-09")
    payment = insert_txn(conn, acct, merchant="Payment", amount=-10000, type="payment", date="2026-09-08")
    return split, plain, payment


def test_transactions_carry_share_fields(client, conn, make_account):
    split, plain, _ = seed(conn, make_account)
    items = {t["id"]: t for t in client.get("/api/transactions").json()["items"]}
    s = items[split]
    assert (s["amount"], s["my_share"], s["share_source"], s["effective_amount"]) == (12000, 3000, "manual", 3000)
    p = items[plain]
    assert (p["amount"], p["my_share"], p["share_source"], p["effective_amount"]) == (5000, None, None, 5000)


def test_non_purchases_use_their_amount_as_effective(client, conn, make_account):
    _, _, payment = seed(conn, make_account)
    items = {t["id"]: t for t in client.get("/api/transactions").json()["items"]}
    assert items[payment]["effective_amount"] == -10000


def test_sort_by_amount_uses_the_share(client, conn, make_account):
    split, plain, payment = seed(conn, make_account)
    desc = client.get("/api/transactions", params={"sort": "amount", "order": "desc"}).json()["items"]
    assert [t["id"] for t in desc] == [plain, split, payment]  # 5000, 3000 (not 12000), -10000


def test_amount_filters_use_the_share(client, conn, make_account):
    split, plain, _ = seed(conn, make_account)

    def ids(**params):
        return {t["id"] for t in client.get("/api/transactions", params=params).json()["items"]}

    assert ids(min_amount=4000) == {plain}            # the $120 charge is only $30 to the user
    assert ids(max_amount=3000, min_amount=1) == {split}
    assert ids(min_amount=10000) == set()
