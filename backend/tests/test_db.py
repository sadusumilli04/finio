import sqlite3

import pytest

from finio.db import DEFAULT_CATEGORIES, connect, init_db


def test_init_creates_tables(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"accounts", "import_batches", "transactions", "categories",
            "category_rules", "merchant_aliases"} <= names


def test_categories_seeded_from_apple_labels(conn):
    names = [r["name"] for r in conn.execute("SELECT name FROM categories ORDER BY name")]
    assert names == sorted(DEFAULT_CATEGORIES)
    assert "Other" in names


def test_init_is_idempotent(conn):
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == len(DEFAULT_CATEGORIES)


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO transactions(account_id, transaction_date, amount, type, category_id, "
            "category_source, origin) VALUES (999, '2026-01-01', 100, 'purchase', 1, 'manual', 'manual')"
        )


def test_fingerprint_occurrence_unique_but_nulls_allowed(conn, make_account):
    acct = make_account()
    cat = conn.execute("SELECT id FROM categories LIMIT 1").fetchone()["id"]
    sql = (
        "INSERT INTO transactions(account_id, transaction_date, amount, type, category_id, "
        "category_source, origin, fingerprint, occurrence) VALUES (?, '2026-01-01', 100, 'purchase', ?, "
        "'source_default', 'import', ?, ?)"
    )
    conn.execute(sql, (acct, cat, "abc", 1))
    conn.execute(sql, (acct, cat, "abc", 2))  # same fingerprint, new occurrence: ok
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (acct, cat, "abc", 1))
    conn.execute(sql, (acct, cat, None, None))
    conn.execute(sql, (acct, cat, None, None))  # manual rows have NULL fingerprints


def test_schema_version_stamped_and_not_lowered(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.execute("PRAGMA user_version = 5")
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5


def test_transactions_have_split_columns(conn):
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
    assert {"my_share", "share_source"} <= columns


def test_split_column_constraints(conn, make_account):
    acct = make_account()
    sql = (
        "INSERT INTO transactions(account_id, transaction_date, amount, type, category_id, "
        "category_source, origin, my_share, share_source) "
        "VALUES (?, '2026-01-01', 1000, 'purchase', 1, 'manual', 'manual', ?, ?)"
    )
    conn.execute(sql, (acct, 250, "manual"))
    conn.execute(sql, (acct, 0, "venmo"))
    conn.execute(sql, (acct, None, None))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (acct, -1, "manual"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (acct, 250, "bogus"))


OLD_TRANSACTIONS_DDL = """
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    batch_id INTEGER REFERENCES import_batches(id),
    posted_date TEXT,
    transaction_date TEXT NOT NULL,
    amount INTEGER NOT NULL,
    type TEXT NOT NULL,
    raw_description TEXT,
    merchant_raw TEXT,
    merchant_clean TEXT,
    cardholder TEXT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    category_source TEXT NOT NULL CHECK (category_source IN ('source_default','rule','manual')),
    source_category TEXT,
    origin TEXT NOT NULL CHECK (origin IN ('import','manual')),
    fingerprint TEXT,
    occurrence INTEGER,
    raw_row TEXT
);
"""


@pytest.mark.parametrize("version", [0, 1])
def test_migrates_an_old_database_in_place(tmp_path, version):
    path = tmp_path / "old.sqlite3"
    raw = sqlite3.connect(path)
    raw.executescript(OLD_TRANSACTIONS_DDL)
    raw.execute(
        "INSERT INTO transactions(account_id, transaction_date, amount, type, merchant_clean, "
        "category_id, category_source, origin) VALUES (1, '2026-09-01', 12000, 'purchase', 'Home Plate', "
        "1, 'source_default', 'import')"
    )
    raw.execute(f"PRAGMA user_version = {version}")
    raw.commit()
    raw.close()

    conn = connect(path)
    init_db(conn)
    row = conn.execute("SELECT * FROM transactions").fetchone()
    assert (row["merchant_clean"], row["amount"]) == ("Home Plate", 12000)
    assert row["my_share"] is None and row["share_source"] is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2

    init_db(conn)  # a second run changes nothing
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()
