from pathlib import Path

from finio.services.ingestion import import_file

FIXTURE = (Path(__file__).parent / "fixtures" / "venmo_sample.csv").read_bytes()


def make_venmo(client, name="Venmo"):
    r = client.post("/api/accounts", json={"name": name, "type": "other", "source": "venmo_csv"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_import_creates_the_category_and_counts_only_payments_you_send_as_spending(client):
    acct = make_venmo(client)
    r = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("v.csv", FIXTURE)})
    assert r.status_code in (200, 201), r.text
    summary = r.json()
    assert (summary["rows_total"], summary["rows_added"], summary["rows_skipped"], summary["flagged"]) == (7, 7, 0, 0)
    assert len(summary["errors"]) == 1  # the cancelled payment
    names = [c["name"] for c in client.get("/api/categories").json()]
    assert "Friends & Family" in names
    spending = client.get("/api/analytics/spending-by-category").json()
    assert {c["category"]: c["total"] for c in spending} == {"Friends & Family": 2340 + 825 + 125000 + 750}


def test_reimporting_the_same_file_is_rejected_and_an_overlapping_one_adds_only_new_rows(client):
    acct = make_venmo(client)
    files = {"file": ("v.csv", FIXTURE)}
    assert client.post("/api/imports", data={"account_id": acct["id"]}, files=files).status_code in (200, 201)
    dup = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("v.csv", FIXTURE)})
    assert dup.status_code == 409
    extra = FIXTURE.replace(
        b",1000000000000000008,",
        b",1000000000000000009,2026-09-17T10:00:00,Payment,Complete,tacos,Test User,Person Five,- $12.00,,0,,0,,"
        b"\"TEST BANK Checking *0000\",,,,,Venmo,,\n,1000000000000000008,",
    )
    assert extra != FIXTURE
    r = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("v2.csv", extra)})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert (body["rows_added"], body["rows_skipped"]) == (1, 7)


def test_a_rule_on_the_note_categorizes_venmo_rows(conn, make_account):
    acct = make_account(source="venmo_csv", name="Venmo", type="other")
    grocery = conn.execute("SELECT id FROM categories WHERE name = 'Grocery'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules(match_field, match_type, pattern, category_id, priority) "
        "VALUES ('description', 'contains', 'groceries', ?, 1)",
        (grocery,),
    )
    conn.commit()
    import_file(conn, acct, "v.csv", FIXTURE)
    row = conn.execute(
        "SELECT c.name AS category, t.category_source FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.raw_description = 'groceries'"
    ).fetchone()
    assert (row["category"], row["category_source"]) == ("Grocery", "rule")


def test_transfers_and_money_in_are_excluded_from_spending_but_kept(conn, make_account):
    acct = make_account(source="venmo_csv", name="Venmo", type="other")
    import_file(conn, acct, "v.csv", FIXTURE)
    types = {r["type"]: r["n"] for r in conn.execute("SELECT type, COUNT(*) AS n FROM transactions GROUP BY type")}
    assert types == {"purchase": 4, "payment": 2, "transfer": 1}


def test_wrong_file_for_a_venmo_account_is_a_400(client):
    acct = make_venmo(client)
    apple = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()
    r = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", apple)})
    assert r.status_code == 400 and "Not a Venmo CSV" in r.json()["detail"]
