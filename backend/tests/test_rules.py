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


def test_blank_or_missing_source_category_falls_back_to_other(conn):
    # Test None
    cid, src = resolve_category(conn, [], "X", "X", None)
    assert (cid, src) == (cat_id(conn, "Other"), "source_default")
    # Test empty string
    cid, src = resolve_category(conn, [], "X", "X", "")
    assert (cid, src) == (cat_id(conn, "Other"), "source_default")
    # Test whitespace-only
    cid, src = resolve_category(conn, [], "X", "X", "   ")
    assert (cid, src) == (cat_id(conn, "Other"), "source_default")


def test_unknown_source_category_creates_it(conn):
    cid, src = resolve_category(conn, [], "X", "X", "  Health & Fitness ")
    assert src == "source_default"
    # Verify the category was created with the exact stripped label
    created = conn.execute("SELECT * FROM categories WHERE name = ?", ("Health & Fitness",)).fetchone()
    assert created is not None
    assert created["id"] == cid


def test_unknown_source_category_reused_not_duplicated(conn):
    # First call creates the category
    cid1, _ = resolve_category(conn, [], "X", "X", "New Category")
    # Second call with same label should reuse it
    cid2, _ = resolve_category(conn, [], "X", "X", "New Category")
    assert cid1 == cid2
    # Third call with different case should also reuse it
    cid3, _ = resolve_category(conn, [], "X", "X", "NEW CATEGORY")
    assert cid1 == cid3
    # Verify exactly one row with that name exists
    count = conn.execute("SELECT COUNT(*) FROM categories WHERE lower(name) = lower(?)", ("New Category",)).fetchone()[0]
    assert count == 1


def test_rule_match_does_not_create_category(conn):
    # Add a rule
    add_rule(conn, "target", "Shopping")
    rules = load_rules(conn)
    # Call with a matching rule and an unknown source label
    cid, src = resolve_category(conn, rules, "Target", "TARGET T-1", "Unknown Category")
    # Should return the rule's category
    assert (cid, src) == (cat_id(conn, "Shopping"), "rule")
    # Verify the unknown category was NOT created
    unknown = conn.execute("SELECT * FROM categories WHERE name = ?", ("Unknown Category",)).fetchone()
    assert unknown is None


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
