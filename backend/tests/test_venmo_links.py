import pytest

from finio.db import connect, init_db
from finio.errors import ConflictError, NotFoundError, ValidationFailed
from finio.services import analytics
from finio.services import transactions as tx
from finio.services.accounts import delete_account
from finio.services.venmo_links import link_payment, list_candidates, list_links, unlink_payment
from tests.helpers import insert_txn


def setup(conn, make_account):
    card = make_account()
    venmo = make_account(source="venmo_csv", name="Venmo", type="other")
    return card, venmo


def charge(conn, card, amount=18000, date="2026-09-10", **kw):
    return insert_txn(conn, card, date=date, amount=amount, merchant="Dinner Place", category="Restaurants", **kw)


def payin(conn, venmo, amount=4500, date="2026-09-11", who="Person One"):
    return insert_txn(conn, venmo, date=date, amount=-amount, type="payment", merchant=who, description="dinner")


def test_link_one_payment_sets_share(conn, make_account):
    card, venmo = setup(conn, make_account)
    c, p = charge(conn, card), payin(conn, venmo)
    result = link_payment(conn, c, p)
    assert result["id"] == c
    assert result["my_share"] == 13500
    assert result["share_source"] == "venmo"
    assert result["venmo_link_count"] == 1
    assert tx.get_transaction(conn, p)["venmo_linked_to"] == c


def test_several_links_and_unlink(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card)
    ps = [payin(conn, venmo) for _ in range(3)]
    for p in ps:
        link_payment(conn, c, p)
    assert tx.get_transaction(conn, c)["my_share"] == 4500
    assert unlink_payment(conn, c, ps[0])["my_share"] == 9000
    unlink_payment(conn, c, ps[1])
    last = unlink_payment(conn, c, ps[2])
    assert last["my_share"] is None and last["share_source"] is None
    assert last["venmo_link_count"] == 0


def test_link_refusals(conn, make_account):
    card, venmo = setup(conn, make_account)
    c, p = charge(conn, card), payin(conn, venmo)
    refund = insert_txn(conn, card, amount=-500, type="refund")
    venmo_purchase = insert_txn(conn, venmo, amount=2000, type="purchase")
    venmo_charge = insert_txn(conn, venmo, amount=2000, type="purchase")
    card_payment = insert_txn(conn, card, amount=-500, type="payment")

    with pytest.raises(ValidationFailed, match="Only a purchase on a non-Venmo account"):
        link_payment(conn, refund, p)
    with pytest.raises(ValidationFailed, match="Only a purchase on a non-Venmo account"):
        link_payment(conn, venmo_charge, p)
    with pytest.raises(ValidationFailed, match="Only an incoming Venmo payment"):
        link_payment(conn, c, venmo_purchase)
    with pytest.raises(ValidationFailed, match="Only an incoming Venmo payment"):
        link_payment(conn, c, card_payment)

    with pytest.raises(NotFoundError):
        link_payment(conn, 9999, p)
    with pytest.raises(NotFoundError):
        link_payment(conn, c, 9999)
    with pytest.raises(NotFoundError):
        unlink_payment(conn, c, p)

    link_payment(conn, c, p)
    c2 = charge(conn, card)
    with pytest.raises(ConflictError, match="already linked"):
        link_payment(conn, c2, p)
    assert tx.get_transaction(conn, p)["venmo_linked_to"] == c
    assert tx.get_transaction(conn, c2)["venmo_link_count"] == 0
    with pytest.raises(NotFoundError):
        unlink_payment(conn, c2, p)

    big = payin(conn, venmo, amount=14000)
    with pytest.raises(ValidationFailed, match="would exceed the charge"):
        link_payment(conn, c, big)
    assert tx.get_transaction(conn, c)["my_share"] == 13500
    assert tx.get_transaction(conn, c)["venmo_link_count"] == 1


def test_link_replaces_manual_share_and_unlink_clears(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card, my_share=10000)
    assert tx.get_transaction(conn, c)["share_source"] == "manual"
    p = payin(conn, venmo)
    assert link_payment(conn, c, p)["share_source"] == "venmo"
    after = unlink_payment(conn, c, p)
    assert after["my_share"] is None and after["share_source"] is None


def test_manual_split_edits_refused_while_linked(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card, origin="manual")
    link_payment(conn, c, payin(conn, venmo))
    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.set_share(conn, c, 100)
    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.update_transaction(conn, c, {"my_share": 100})
    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.update_transaction(conn, c, {"amount": 20000})
    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.update_transaction(conn, c, {"direction": "refund"})
    cat = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]
    assert tx.update_transaction(conn, c, {"category_id": cat})["category"] == "Shopping"
    assert tx.get_transaction(conn, c)["my_share"] == 13500


def test_resending_unchanged_amount_and_direction_while_linked_succeeds(conn, make_account):
    """The edit form always resends amount and direction on every save; only an actual change to
    amount/direction (or setting my_share at all) should be refused while linked."""
    card, venmo = setup(conn, make_account)
    c = charge(conn, card, origin="manual", amount=18000)
    link_payment(conn, c, payin(conn, venmo))
    cat = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]

    result = tx.update_transaction(
        conn, c, {"amount": 18000, "direction": "expense", "category_id": cat}
    )
    assert result["category"] == "Shopping"
    assert result["my_share"] == 13500
    assert result["venmo_link_count"] == 1

    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.update_transaction(conn, c, {"amount": 20000, "direction": "expense"})
    with pytest.raises(ValidationFailed, match="Unlink the Venmo payments first"):
        tx.update_transaction(conn, c, {"amount": 18000, "direction": "refund"})
    assert tx.get_transaction(conn, c)["my_share"] == 13500


def test_candidates_window_and_order(conn, make_account):
    card, venmo = setup(conn, make_account)
    other_card = make_account(name="Other")
    c = charge(conn, card, date="2026-09-10")
    in_m3 = payin(conn, venmo, date="2026-09-07", amount=1000)
    out_m4 = payin(conn, venmo, date="2026-09-06")
    in_p30 = payin(conn, venmo, date="2026-10-10", amount=1000)
    out_p31 = payin(conn, venmo, date="2026-10-11")
    same_small = payin(conn, venmo, date="2026-09-10", amount=500)
    same_big = payin(conn, venmo, date="2026-09-10", amount=900)
    insert_txn(conn, other_card, date="2026-09-10", amount=-500, type="payment")
    insert_txn(conn, venmo, date="2026-09-10", amount=700, type="purchase")

    cands = list_candidates(conn, c)
    ids = [x["id"] for x in cands]
    assert ids == [same_big, same_small, in_m3, in_p30]
    assert out_m4 not in ids and out_p31 not in ids
    assert cands[0] == {"id": same_big, "date": "2026-09-10", "merchant": "Person One",
                        "description": "dinner", "amount": 900}

    link_payment(conn, c, same_big)
    assert same_big not in [x["id"] for x in list_candidates(conn, c)]
    assert [x["id"] for x in list_links(conn, c)] == [same_big]
    with pytest.raises(NotFoundError):
        list_candidates(conn, 9999)
    with pytest.raises(ValidationFailed):
        list_candidates(conn, in_m3)


def test_list_links_oldest_first(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card)
    late = payin(conn, venmo, date="2026-09-12")
    early = payin(conn, venmo, date="2026-09-10")
    link_payment(conn, c, late)
    link_payment(conn, c, early)
    assert [x["id"] for x in list_links(conn, c)] == [early, late]


def test_delete_venmo_account_clears_links_and_share(conn, make_account):
    card, venmo = setup(conn, make_account)
    c, p = charge(conn, card), payin(conn, venmo)
    link_payment(conn, c, p)
    delete_account(conn, venmo)
    assert conn.execute("SELECT COUNT(*) FROM venmo_links").fetchone()[0] == 0
    row = tx.get_transaction(conn, c)
    assert row["my_share"] is None and row["share_source"] is None and row["venmo_link_count"] == 0


def test_delete_venmo_account_keeps_manual_share_only_when_no_links(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card, my_share=7000)
    delete_account(conn, venmo)
    assert tx.get_transaction(conn, c)["my_share"] == 7000


def test_delete_card_account_unlinks_payments(conn, make_account):
    card, venmo = setup(conn, make_account)
    c, p = charge(conn, card), payin(conn, venmo)
    link_payment(conn, c, p)
    delete_account(conn, card)
    assert conn.execute("SELECT COUNT(*) FROM venmo_links").fetchone()[0] == 0
    assert tx.get_transaction(conn, p)["venmo_linked_to"] is None
    assert [x["id"] for x in list_candidates(conn, insert_txn(conn, make_account(name="C2"), date="2026-09-10"))] == [p]


def test_dashboard_reflects_linked_share(conn, make_account):
    card, venmo = setup(conn, make_account)
    c = charge(conn, card)
    link_payment(conn, c, payin(conn, venmo))
    rows = analytics.spending_by_category(conn)
    restaurants = next(r for r in rows if r["category"] == "Restaurants")
    assert restaurants["total"] == 13500


def test_init_db_adds_table_to_old_database(tmp_path):
    conn = connect(tmp_path / "old.sqlite3")
    init_db(conn)
    conn.execute("DROP TABLE venmo_links")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    init_db(conn)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "venmo_links" in tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    conn.close()
