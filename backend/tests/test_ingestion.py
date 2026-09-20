import json
from pathlib import Path

import pytest

from finio.errors import ConflictError, NotFoundError, ValidationFailed
from finio.services.ingestion import import_file

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()
LINES = FIXTURE.decode().splitlines(keepends=True)


def count(conn):
    return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def test_imports_fixture(conn, make_account):
    acct = make_account()
    s = import_file(conn, acct, "sample.csv", FIXTURE)
    assert (s.rows_total, s.rows_added, s.rows_skipped, s.errors) == (6, 6, 0, [])
    assert count(conn) == 6
    batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (s.batch_id,)).fetchone()
    assert batch["rows_added"] == 6 and batch["filename"] == "sample.csv"


def test_same_file_twice_rejected(conn, make_account):
    acct = make_account()
    import_file(conn, acct, "a.csv", FIXTURE)
    with pytest.raises(ConflictError):
        import_file(conn, acct, "a.csv", FIXTURE)
    assert count(conn) == 6


def test_overlapping_export_skips_seen_rows_and_keeps_identical_purchases(conn, make_account):
    acct = make_account()
    first = "".join(LINES[:5])  # header + 4 rows, including both Blue Bottle coffees
    s1 = import_file(conn, acct, "part1.csv", first.encode())
    assert s1.rows_added == 4
    s2 = import_file(conn, acct, "full.csv", FIXTURE)
    assert (s2.rows_added, s2.rows_skipped) == (2, 4)
    assert count(conn) == 6
    coffees = conn.execute("SELECT COUNT(*) FROM transactions WHERE merchant_raw='Blue Bottle'").fetchone()[0]
    assert coffees == 2


def test_source_category_and_cleaned_merchant_and_raw_row(conn, make_account):
    acct = make_account()
    import_file(conn, acct, "a.csv", FIXTURE)
    row = conn.execute(
        "SELECT t.*, c.name AS cat FROM transactions t JOIN categories c ON c.id=t.category_id "
        "WHERE merchant_raw LIKE 'Flik%'"
    ).fetchone()
    assert row["cat"] == "Restaurants" and row["category_source"] == "source_default"
    assert row["merchant_clean"] == "Flik Cafe Az Qps"
    assert row["origin"] == "import" and row["amount"] == 1044
    assert json.loads(row["raw_row"])["Merchant"] == "Flik Cafe Az       Qps"


def test_alias_and_rule_applied_on_import(conn, make_account):
    acct = make_account()
    conn.execute("INSERT INTO merchant_aliases(pattern, clean_name) VALUES ('flik cafe', 'Flik Cafe')")
    shopping = conn.execute("SELECT id FROM categories WHERE name='Shopping'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules(match_field, match_type, pattern, category_id) "
        "VALUES ('merchant','contains','netflix',?)", (shopping,),
    )
    conn.commit()
    import_file(conn, acct, "a.csv", FIXTURE)
    flik = conn.execute("SELECT merchant_clean FROM transactions WHERE merchant_raw LIKE 'Flik%'").fetchone()
    assert flik["merchant_clean"] == "Flik Cafe"
    nf = conn.execute("SELECT category_id, category_source FROM transactions WHERE merchant_raw='Netflix'").fetchone()
    assert (nf["category_id"], nf["category_source"]) == (shopping, "rule")


def test_bad_rows_reported_rest_imported(conn, make_account):
    acct = make_account()
    bad = LINES[0] + '99/99/2026,,"X","Shop","Shopping","Purchase","1.00","A"\n' + LINES[1]
    s = import_file(conn, acct, "bad.csv", bad.encode())
    assert s.rows_added == 1 and [e.line for e in s.errors] == [2]


def test_flagged_count(conn, make_account):
    acct = make_account()
    row = '09/01/2026,09/02/2026,"X","Shop","Shopping","Mystery","1.00","A"\n'
    s = import_file(conn, acct, "f.csv", (LINES[0] + row).encode())
    assert s.flagged == 1 and s.rows_added == 1


def test_errors(conn, make_account):
    with pytest.raises(NotFoundError):
        import_file(conn, 999, "a.csv", FIXTURE)
    manual = make_account(source="manual", name="Bank")
    with pytest.raises(ValidationFailed):
        import_file(conn, manual, "a.csv", FIXTURE)
    acct = make_account()
    with pytest.raises(ValidationFailed):
        import_file(conn, acct, "junk.csv", b"a,b\n1,2\n")
    assert conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0


def test_unknown_csv_category_becomes_a_category(conn, make_account):
    acct = make_account()
    import_file(conn, acct, "sample.csv", FIXTURE)
    # The payment row has category "Payment" which is not seeded
    payment = conn.execute(
        "SELECT t.*, c.name AS cat FROM transactions t JOIN categories c ON c.id=t.category_id "
        "WHERE merchant_raw = 'Payment'"
    ).fetchone()
    assert payment is not None
    assert payment["cat"] == "Payment"
    assert payment["category_source"] == "source_default"
    # Verify the Target row still has Grocery
    target = conn.execute(
        "SELECT t.*, c.name AS cat FROM transactions t JOIN categories c ON c.id=t.category_id "
        "WHERE merchant_raw LIKE 'Target%'"
    ).fetchone()
    assert target["cat"] == "Grocery"


def test_import_rolls_back_new_categories_on_failure(conn, make_account):
    acct = make_account()
    # Create a CSV with two rows where the first has an unknown category
    csv_content = (
        "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By\n"
        '09/18/2026,09/19/2026,"TEST1","Test1","Zzz Unknown","Purchase","29.77","Test Person A"\n'
        '09/18/2026,09/19/2026,"TEST2","Test2","Restaurants","Purchase","10.44","Test Person B"\n'
    ).encode()

    # Monkeypatch clean_merchant to raise RuntimeError on its second call
    from finio.services import ingestion
    original_clean_merchant = ingestion.clean_merchant
    call_count = [0]

    def mock_clean_merchant(raw, aliases):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("Simulated failure")
        return original_clean_merchant(raw, aliases)

    ingestion.clean_merchant = mock_clean_merchant
    try:
        with pytest.raises(RuntimeError, match="Simulated failure"):
            import_file(conn, acct, "test.csv", csv_content)

        # Verify no category named "Zzz Unknown" exists
        zzz = conn.execute("SELECT * FROM categories WHERE name = ?", ("Zzz Unknown",)).fetchone()
        assert zzz is None
        # Verify no transactions were stored
        txn_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert txn_count == 0
        # Verify no import batch was stored
        batch_count = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        assert batch_count == 0
    finally:
        ingestion.clean_merchant = original_clean_merchant
