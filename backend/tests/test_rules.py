from finio.services.rules import load_rules, reapply_rules, resolve_category, rule_matches
from tests.helpers import insert_txn


def cat_id(conn, name):
    return conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()["id"]


def add_rule(conn, pattern, category, field="merchant", type_="contains", priority=100):
    conn.execute(
        "INSERT INTO category_rules(match_field, match_type, pattern, category_id, priority) "
        "VALUES (?,?,?,?,?)",
        (field, type_, pattern, cat_id(conn, category), priority),
    )
    conn.commit()


def test_contains_and_equals_case_insensitive(conn):
    add_rule(conn, "target", "Grocery")
    add_rule(conn, "netflix", "Entertainment", type_="equals")
    contains, equals = load_rules(conn)
    assert rule_matches(contains, "Super TARGET store", None)
    assert not rule_matches(equals, "Netflix Premium", None)
    assert rule_matches(equals, "NETFLIX", None)


def test_description_field(conn):
    add_rule(conn, "ach deposit", "Other", field="description")
    (rule,) = load_rules(conn)
    assert rule_matches(rule, "Payment", "ACH DEPOSIT INTERNET")
    assert not rule_matches(rule, "ach deposit", "something else")


def test_rule_beats_source_category(conn):
    add_rule(conn, "target", "Shopping")
    cid, src = resolve_category(conn, load_rules(conn), "Target", "TARGET T-1", "Grocery")
    assert (cid, src) == (cat_id(conn, "Shopping"), "rule")


def test_lower_priority_number_wins(conn):
    add_rule(conn, "shop", "Shopping", priority=200)
    add_rule(conn, "shop", "Grocery", priority=10)
    cid, _ = resolve_category(conn, load_rules(conn), "Shop", "", None)
    assert cid == cat_id(conn, "Grocery")


def test_source_category_used_when_no_rule(conn):
    cid, src = resolve_category(conn, [], "X", "X", "grocery")
    assert (cid, src) == (cat_id(conn, "Grocery"), "source_default")


def test_falls_back_to_other(conn):
    cid, src = resolve_category(conn, [], "X", "X", "Never Heard Of It")
    assert (cid, src) == (cat_id(conn, "Other"), "source_default")
    cid, _ = resolve_category(conn, [], "X", "X", None)
    assert cid == cat_id(conn, "Other")


def test_reapply_skips_manual_and_updates_others(conn, make_account):
    acct = make_account()
    a = insert_txn(conn, acct, merchant="Target Store", category="Other")
    b = insert_txn(conn, acct, merchant="Target Store", category="Other",
                   category_source="manual", origin="manual")
    c = insert_txn(conn, acct, merchant="Unrelated", category="Other")
    add_rule(conn, "target", "Grocery")
    assert reapply_rules(conn) == 1
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM transactions")}
    assert rows[a]["category_id"] == cat_id(conn, "Grocery") and rows[a]["category_source"] == "rule"
    assert rows[b]["category_id"] == cat_id(conn, "Other") and rows[b]["category_source"] == "manual"
    assert rows[c]["category_id"] == cat_id(conn, "Other")
