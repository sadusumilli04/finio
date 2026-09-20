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
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.execute("PRAGMA user_version = 5")
    init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
