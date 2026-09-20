import sqlite3
from pathlib import Path

DEFAULT_CATEGORIES = [
    "Entertainment", "Grocery", "Insurance", "Other",
    "Restaurants", "Shopping", "Transportation", "Utilities",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('credit_card','checking','savings','other')),
    source TEXT NOT NULL,
    starting_balance INTEGER NOT NULL DEFAULT 0,
    starting_balance_date TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_added INTEGER NOT NULL DEFAULT 0,
    rows_skipped INTEGER NOT NULL DEFAULT 0,
    UNIQUE (account_id, file_hash)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY,
    match_field TEXT NOT NULL CHECK (match_field IN ('merchant','description')),
    match_type TEXT NOT NULL CHECK (match_type IN ('contains','equals')),
    pattern TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    priority INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS merchant_aliases (
    id INTEGER PRIMARY KEY,
    pattern TEXT NOT NULL,
    clean_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
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

CREATE UNIQUE INDEX IF NOT EXISTS ux_txn_fingerprint
    ON transactions(fingerprint, occurrence) WHERE fingerprint IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_txn_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS ix_txn_merchant ON transactions(merchant_clean);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO categories(name) VALUES (?)", [(n,) for n in DEFAULT_CATEGORIES]
        )
    conn.commit()
