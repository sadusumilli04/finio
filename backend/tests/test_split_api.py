from pathlib import Path

from finio.services.transactions import set_share
from tests.helpers import insert_txn

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()
LINES = FIXTURE.decode().splitlines(keepends=True)


def cat(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def manual_account(client):
    return client.post("/api/accounts", json={"name": "Chase", "type": "checking", "source": "manual"}).json()["id"]


def create_manual(client, acct, amount=5000, direction="expense", merchant="Dinner"):
    r = client.post("/api/transactions", json={
        "account_id": acct, "date": "2026-09-10", "amount": amount, "direction": direction,
        "merchant": merchant, "category_id": cat(client, "Restaurants"),
    })
    assert r.status_code == 201, r.text
    return r.json()


def patch(client, tid, **body):
    return client.patch(f"/api/transactions/{tid}", json=body)


def test_imported_purchase_can_be_split(client, conn, make_account):
    tid = insert_txn(conn, make_account(), amount=12000, merchant="Home Plate")
    r = patch(client, tid, my_share=3000)
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["my_share"], t["share_source"], t["effective_amount"], t["amount"]) == (3000, "manual", 3000, 12000)


def test_share_boundaries(client, conn, make_account):
    tid = insert_txn(conn, make_account(), amount=12000)
    assert patch(client, tid, my_share=12000).status_code == 200    # the whole charge
    assert patch(client, tid, my_share=0).json()["effective_amount"] == 0   # fully repaid
    assert patch(client, tid, my_share=12001).status_code == 400
    assert patch(client, tid, my_share=-1).status_code == 400
    assert client.get("/api/transactions").json()["items"][0]["my_share"] == 0   # rejected edits changed nothing


def test_null_clears_the_split(client, conn, make_account):
    tid = insert_txn(conn, make_account(), amount=12000, my_share=3000)
    t = patch(client, tid, my_share=None).json()
    assert (t["my_share"], t["share_source"], t["effective_amount"]) == (None, None, 12000)


def test_only_purchases_can_be_split(client, conn, make_account):
    acct = make_account()
    payment = insert_txn(conn, acct, amount=-10000, type="payment")
    assert patch(client, payment, my_share=500).status_code == 400
    refund = create_manual(client, manual_account(client), direction="refund")
    assert patch(client, refund["id"], my_share=100).status_code == 400
    assert patch(client, payment, my_share=None).status_code == 200   # clearing is always fine


def test_imported_rows_stay_read_only_except_category_and_share(client, conn, make_account):
    tid = insert_txn(conn, make_account(), amount=12000, merchant="Home Plate")
    assert patch(client, tid, merchant="X").status_code == 403
    assert patch(client, tid, my_share=3000, merchant="X").status_code == 403
    both = patch(client, tid, my_share=3000, category_id=cat(client, "Grocery"))
    assert both.status_code == 200 and both.json()["category"] == "Grocery"


def test_unknown_transaction_is_404(client):
    assert patch(client, 9999, my_share=100).status_code == 404


def test_manual_create_ignores_my_share(client):
    acct = manual_account(client)
    r = client.post("/api/transactions", json={
        "account_id": acct, "date": "2026-09-10", "amount": 5000, "direction": "expense",
        "merchant": "Dinner", "category_id": cat(client, "Restaurants"), "my_share": 100,
    })
    assert r.status_code == 201
    assert (r.json()["my_share"], r.json()["effective_amount"]) == (None, 5000)


def test_manual_amount_edits_respect_the_split(client):
    t = create_manual(client, manual_account(client), amount=5000)
    assert patch(client, t["id"], my_share=2000).status_code == 200
    assert patch(client, t["id"], amount=1500).status_code == 400            # below the share
    assert patch(client, t["id"], amount=3000).json()["my_share"] == 2000    # still fits
    both = patch(client, t["id"], amount=1000, my_share=800)
    assert both.status_code == 200 and both.json()["effective_amount"] == 800
    assert patch(client, t["id"], amount=900, my_share=1500).status_code == 400
    assert client.get("/api/transactions").json()["items"][0]["amount"] == 1000   # unchanged by the failed edit


def test_manual_direction_change_clears_the_split(client):
    t = create_manual(client, manual_account(client), amount=5000)
    patch(client, t["id"], my_share=2000)
    changed = patch(client, t["id"], direction="income").json()
    assert (changed["type"], changed["my_share"], changed["share_source"]) == ("income", None, None)
    assert changed["effective_amount"] == -5000


def test_reimport_keeps_existing_splits(client):
    acct = client.post("/api/accounts", json={"name": "Apple", "type": "credit_card", "source": "apple_card_csv"}).json()["id"]
    first = "".join(LINES[:3]).encode()
    client.post("/api/imports", data={"account_id": acct}, files={"file": ("part.csv", first)})
    target = next(t for t in client.get("/api/transactions").json()["items"] if t["merchant"] == "Target")
    patch(client, target["id"], my_share=1000)
    client.post("/api/imports", data={"account_id": acct}, files={"file": ("full.csv", FIXTURE)})
    after = next(t for t in client.get("/api/transactions").json()["items"] if t["id"] == target["id"])
    assert after["my_share"] == 1000


def test_rules_never_touch_a_split(client, conn, make_account):
    tid = insert_txn(conn, make_account(), merchant="Target Store", amount=8000, my_share=2000)
    client.post("/api/rules", json={"match_field": "merchant", "match_type": "contains", "pattern": "target",
                                    "category_id": cat(client, "Grocery")})
    assert client.post("/api/rules/reapply").status_code == 200
    item = next(t for t in client.get("/api/transactions").json()["items"] if t["id"] == tid)
    assert (item["category"], item["my_share"]) == ("Grocery", 2000)


def test_set_share_is_the_hook_for_other_sources(conn, make_account):
    tid = insert_txn(conn, make_account(), amount=12000)
    t = set_share(conn, tid, 4000, source="venmo")
    assert (t["my_share"], t["share_source"], t["effective_amount"]) == (4000, "venmo", 4000)
    assert set_share(conn, tid, None)["share_source"] is None
