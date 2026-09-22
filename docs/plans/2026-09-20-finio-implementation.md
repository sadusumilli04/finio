# Finio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that imports Apple Card CSV exports (plus manually entered transactions), categorizes them with user rules, and shows Mint-style spending analysis.

**Architecture:** Layered Python backend (importers → ingestion service → SQLite → FastAPI routes) with a React/TypeScript UI that talks only to the `/api` routes. Each source is a pluggable importer emitting a normalized `RawTransaction`. Raw CSV rows are stored on each imported transaction.

**Tech Stack:** Python 3.13, FastAPI, stdlib `sqlite3`, pytest + httpx; React + TypeScript (Vite), react-router-dom, Recharts, Vitest. Node 22.

**Spec:** `docs/SPECIFICATION.md`

## Global Constraints

- Local only: data lives in a SQLite file (`backend/data/finio.sqlite3`, git-ignored); no auth, hosting, or third-party sync.
- Amounts are integer cents; positive = money spent, negative = money in (payments, refunds, income).
- Dates are stored as ISO `YYYY-MM-DD`; Apple CSV dates are `MM/DD/YYYY`.
- "Spending" in analytics counts only `type = 'purchase'` (excludes payments, refunds, income).
- Manually entered category is required and is never overwritten by rules (`category_source = 'manual'`).
- Imported transactions are read-only except category; only manual transactions can be edited or deleted.
- Never commit real financial data. Test fixtures use fabricated rows only. `*.csv` is git-ignored except `backend/tests/fixtures/`.
- Out of scope for v1: budgets, net-worth view, PDF import, Plaid, auth.
- Every commit message ends with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (pass as a second `-m`).
- Backend commands run from `backend/` using `.venv/bin/...`; frontend commands run from `frontend/`.

---

## File Structure

```
.gitignore
README.md
backend/
  pyproject.toml
  finio/
    __init__.py
    errors.py            # NotFoundError, ForbiddenError, ConflictError, ValidationFailed
    db.py                # connect(), init_db(), schema, seed categories
    main.py              # app = create_app()  (uvicorn entrypoint)
    app.py               # create_app(), error handlers, router wiring
    deps.py              # get_conn dependency
    importers/
      base.py            # RawTransaction, RowError, ParseResult
      apple_card_csv.py  # AppleCardCsvImporter
    services/
      merchants.py       # clean_merchant, load_aliases
      dedup.py           # fingerprint, assign_occurrences
      rules.py           # rule matching, resolve_category, reapply_rules
      ingestion.py       # import_file, IMPORTERS, ImportSummary
      filters.py         # where_clause (shared by transactions + analytics)
      transactions.py    # list/get/create_manual/update/delete
      analytics.py       # by-category, trends, top-merchants
      recurring.py       # detect(), find_recurring()
    api/
      accounts.py  categories.py  imports.py  transactions.py
      rules.py     analytics.py
  tests/
    __init__.py  conftest.py  helpers.py
    fixtures/apple_sample.csv
    test_*.py
frontend/
  (Vite React-TS app)
  src/
    api.ts  App.tsx  main.tsx  styles.css
    lib/money.ts  lib/query.ts  lib/useFetch.ts
    components/FilterBar.tsx  components/AddTransactionForm.tsx
    pages/Dashboard.tsx  Transactions.tsx  Recurring.tsx  Import.tsx  Accounts.tsx
```

---

### Task 1: Backend scaffold, schema, seed data

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/finio/__init__.py`, `backend/finio/errors.py`, `backend/finio/db.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/helpers.py`, `backend/tests/test_db.py`

**Interfaces:**
- Produces: `connect(path) -> sqlite3.Connection` (Row factory, FK on, `check_same_thread=False`); `init_db(conn) -> None` (idempotent; creates tables, seeds 8 categories); `DEFAULT_CATEGORIES: list[str]`; exceptions `NotFoundError`, `ForbiddenError`, `ConflictError`, `ValidationFailed` (all subclass `FinioError(Exception)`); pytest fixtures `db_path`, `conn`, `make_account(source="apple_card_csv", name="Test Card", type="credit_card") -> int`; helper `insert_txn(conn, account_id, **kw) -> int`.

- [ ] **Step 1: Create the project skeleton**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
node_modules/
frontend/dist/
backend/data/
*.sqlite3
*.db
.DS_Store
*.csv
!backend/tests/fixtures/*.csv
```

`backend/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "finio"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[tool.setuptools.packages.find]
include = ["finio*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`backend/finio/__init__.py`: empty file. `backend/tests/__init__.py`: empty file.

`backend/finio/errors.py`:
```python
class FinioError(Exception):
    """Base class for errors the API maps to HTTP responses."""


class NotFoundError(FinioError):
    pass


class ForbiddenError(FinioError):
    pass


class ConflictError(FinioError):
    pass


class ValidationFailed(FinioError):
    pass
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
Expected: installs without error.

- [ ] **Step 3: Write the failing tests**

`backend/tests/test_db.py`:
```python
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
```

`backend/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from finio.db import connect, init_db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "finio.sqlite3"


@pytest.fixture
def conn(db_path):
    c = connect(db_path)
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def make_account(conn):
    def _make(source="apple_card_csv", name="Test Card", type="credit_card"):
        cur = conn.execute(
            "INSERT INTO accounts(name, type, source) VALUES (?, ?, ?)", (name, type, source)
        )
        conn.commit()
        return cur.lastrowid

    return _make


@pytest.fixture
def client(db_path):
    from finio.app import create_app

    with TestClient(create_app(db_path)) as c:
        yield c
```

`backend/tests/helpers.py`:
```python
def insert_txn(
    conn,
    account_id,
    *,
    date="2026-09-01",
    amount=1000,
    type="purchase",
    merchant="Shop",
    description=None,
    cardholder=None,
    category="Other",
    origin="import",
    category_source="source_default",
    posted=None,
):
    cat_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO transactions(account_id, posted_date, transaction_date, amount, type, "
        "raw_description, merchant_raw, merchant_clean, cardholder, category_id, category_source, origin) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (account_id, posted, date, amount, type, description or merchant, merchant, merchant,
         cardholder, cat_id, category_source, origin),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError: finio.db`).

- [ ] **Step 5: Implement `db.py`**

`backend/finio/db.py`:
```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`
Expected: 5 PASS. (`conftest.py` imports `TestClient` at module level, which needs `httpx`, installed by the dev extra.)

- [ ] **Step 7: Commit**

```bash
git add .gitignore backend
git commit -m "feat: backend scaffold, SQLite schema, seed categories" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Apple Card CSV importer

**Files:**
- Create: `backend/finio/importers/__init__.py` (empty), `backend/finio/importers/base.py`, `backend/finio/importers/apple_card_csv.py`, `backend/tests/fixtures/apple_sample.csv`, `backend/tests/test_apple_importer.py`

**Interfaces:**
- Produces:
  - `RawTransaction(transaction_date: str, posted_date: str | None, amount: int, type: str, raw_description: str, merchant_raw: str, cardholder: str | None, source_category: str | None, raw_row: dict, flagged: bool = False)` (frozen dataclass; dates ISO)
  - `RowError(line: int, message: str)`; `ParseResult(rows: list[RawTransaction], errors: list[RowError])`
  - `AppleCardCsvImporter().parse(content: bytes) -> ParseResult`; raises `ValueError` if required columns are missing.

- [ ] **Step 1: Create the fabricated fixture**

`backend/tests/fixtures/apple_sample.csv`:
```
Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By
09/18/2026,09/19/2026,"TARGET T-0323 CUPERTINO CA USA","Target","Grocery","Purchase","29.77","Test Person A"
09/18/2026,09/19/2026,"FLIK CAFE AZ QPS GAITHERSBURG MD USA","Flik Cafe Az       Qps","Restaurants","Purchase","10.44","Test Person B"
09/17/2026,09/18/2026,"BLUE BOTTLE COFFEE OAKLAND CA","Blue Bottle","Restaurants","Purchase","5.00","Test Person A"
09/17/2026,09/18/2026,"BLUE BOTTLE COFFEE OAKLAND CA","Blue Bottle","Restaurants","Purchase","5.00","Test Person A"
09/16/2026,09/17/2026,"ACH DEPOSIT INTERNET TRANSFER","Payment","Payment","Payment","-100.00","Test Person A"
09/15/2026,09/16/2026,"NETFLIX.COM LOS GATOS CA","Netflix","Entertainment","Purchase","15.49","Test Person A"
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_apple_importer.py`:
```python
from pathlib import Path

import pytest

from finio.importers.apple_card_csv import AppleCardCsvImporter

FIXTURE = Path(__file__).parent / "fixtures" / "apple_sample.csv"
HEADER = "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By\n"


def parse(text: str):
    return AppleCardCsvImporter().parse(text.encode("utf-8"))


def test_parses_fixture():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    assert result.errors == []
    assert len(result.rows) == 6
    target = result.rows[0]
    assert target.transaction_date == "2026-09-18"
    assert target.posted_date == "2026-09-19"
    assert target.amount == 2977
    assert target.type == "purchase"
    assert target.merchant_raw == "Target"
    assert target.source_category == "Grocery"
    assert target.cardholder == "Test Person A"
    assert target.raw_row["Amount (USD)"] == "29.77"


def test_merchant_whitespace_preserved_in_raw():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    assert result.rows[1].merchant_raw == "Flik Cafe Az       Qps"


def test_payment_is_negative_and_typed():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    payment = result.rows[4]
    assert payment.type == "payment"
    assert payment.amount == -10000


def test_positive_payment_amount_is_normalized_negative():
    row = '09/01/2026,09/02/2026,"PAYMENT","Payment","Payment","Payment","50.00","A"\n'
    assert parse(HEADER + row).rows[0].amount == -5000


def test_refund_is_negative():
    row = '09/01/2026,09/02/2026,"REFUND","Shop","Shopping","Credit","12.00","A"\n'
    r = parse(HEADER + row).rows[0]
    assert (r.type, r.amount) == ("refund", -1200)


def test_unknown_type_flagged_as_other():
    row = '09/01/2026,09/02/2026,"X","Shop","Shopping","Mystery","12.00","A"\n'
    r = parse(HEADER + row).rows[0]
    assert r.type == "other" and r.flagged is True


def test_bad_rows_reported_with_line_numbers_and_skipped():
    text = (
        HEADER
        + '13/45/2026,09/02/2026,"X","Shop","Shopping","Purchase","5.00","A"\n'
        + '09/01/2026,09/02/2026,"X","Shop","Shopping","Purchase","abc","A"\n'
        + '09/01/2026,09/02/2026,"X","Shop","Shopping","Purchase","7.25","A"\n'
    )
    result = parse(text)
    assert [e.line for e in result.errors] == [2, 3]
    assert len(result.rows) == 1 and result.rows[0].amount == 725


def test_missing_clearing_date_is_none():
    row = '09/01/2026,,"X","Shop","Shopping","Purchase","5.00","A"\n'
    assert parse(HEADER + row).rows[0].posted_date is None


def test_missing_columns_raises():
    with pytest.raises(ValueError, match="Apple Card"):
        parse("a,b,c\n1,2,3\n")


def test_utf8_bom_handled():
    data = b"\xef\xbb\xbf" + FIXTURE.read_bytes()
    assert len(AppleCardCsvImporter().parse(data).rows) == 6
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_apple_importer.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement**

`backend/finio/importers/base.py`:
```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawTransaction:
    transaction_date: str
    posted_date: str | None
    amount: int
    type: str
    raw_description: str
    merchant_raw: str
    cardholder: str | None
    source_category: str | None
    raw_row: dict
    flagged: bool = False


@dataclass(frozen=True)
class RowError:
    line: int
    message: str


@dataclass
class ParseResult:
    rows: list[RawTransaction] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
```

`backend/finio/importers/apple_card_csv.py`:
```python
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import ParseResult, RawTransaction, RowError

REQUIRED_COLUMNS = {
    "Transaction Date", "Description", "Merchant", "Category", "Type", "Amount (USD)",
}
TYPE_MAP = {
    "purchase": "purchase",
    "installment": "purchase",
    "payment": "payment",
    "refund": "refund",
    "credit": "refund",
}
MONEY_IN_TYPES = {"payment", "refund"}


def _iso_date(value: str) -> str:
    return datetime.strptime(value.strip(), "%m/%d/%Y").date().isoformat()


def _cents(value: str) -> int:
    return int((Decimal(value.strip()) * 100).to_integral_value())


class AppleCardCsvImporter:
    def parse(self, content: bytes) -> ParseResult:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Not an Apple Card CSV; missing columns: {sorted(missing)}")

        result = ParseResult()
        for row in reader:
            line = reader.line_num
            try:
                result.rows.append(self._parse_row(row))
            except (ValueError, InvalidOperation) as exc:
                result.errors.append(RowError(line=line, message=str(exc) or "invalid row"))
        return result

    def _parse_row(self, row: dict) -> RawTransaction:
        get = lambda key: (row.get(key) or "").strip()  # noqa: E731
        transaction_date = _iso_date(get("Transaction Date"))
        posted = get("Clearing Date")
        posted_date = _iso_date(posted) if posted else None
        amount = _cents(get("Amount (USD)"))

        mapped = TYPE_MAP.get(get("Type").lower())
        flagged = mapped is None
        type_ = mapped or "other"
        if type_ in MONEY_IN_TYPES:
            amount = -abs(amount)

        return RawTransaction(
            transaction_date=transaction_date,
            posted_date=posted_date,
            amount=amount,
            type=type_,
            raw_description=row.get("Description") or "",
            merchant_raw=row.get("Merchant") or "",
            cardholder=get("Purchased By") or None,
            source_category=get("Category") or None,
            raw_row={k: v for k, v in row.items() if k is not None},
            flagged=flagged,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_apple_importer.py -v`
Expected: 10 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat: Apple Card CSV importer" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Merchant cleaning and deduplication helpers

**Files:**
- Create: `backend/finio/services/__init__.py` (empty), `backend/finio/services/merchants.py`, `backend/finio/services/dedup.py`, `backend/tests/test_merchants_dedup.py`

**Interfaces:**
- Consumes: `RawTransaction` (Task 2).
- Produces: `clean_merchant(raw: str, aliases: list[tuple[str, str]]) -> str`; `load_aliases(conn) -> list[tuple[str, str]]` (pattern, clean_name); `fingerprint(account_id: int, r: RawTransaction) -> str` (sha256 hex); `assign_occurrences(fps: list[str]) -> list[int]` (1-based per repeated fingerprint).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_merchants_dedup.py`:
```python
from finio.importers.base import RawTransaction
from finio.services.dedup import assign_occurrences, fingerprint
from finio.services.merchants import clean_merchant, load_aliases


def raw(**over):
    base = dict(
        transaction_date="2026-09-18", posted_date="2026-09-19", amount=500, type="purchase",
        raw_description="COFFEE", merchant_raw="Coffee", cardholder="A",
        source_category="Restaurants", raw_row={},
    )
    base.update(over)
    return RawTransaction(**base)


def test_clean_merchant_collapses_whitespace():
    assert clean_merchant("  Flik Cafe Az       Qps ", []) == "Flik Cafe Az Qps"


def test_clean_merchant_alias_wins_case_insensitive():
    aliases = [("flik cafe", "Flik Cafe")]
    assert clean_merchant("FLIK   CAFE AZ QPS", aliases) == "Flik Cafe"


def test_clean_merchant_handles_none_like_empty():
    assert clean_merchant("", []) == ""


def test_load_aliases(conn):
    conn.execute("INSERT INTO merchant_aliases(pattern, clean_name) VALUES ('sq *', 'Square Vendor')")
    conn.commit()
    assert load_aliases(conn) == [("sq *", "Square Vendor")]


def test_fingerprint_stable_and_sensitive():
    a = fingerprint(1, raw())
    assert a == fingerprint(1, raw())
    assert a != fingerprint(2, raw())
    assert a != fingerprint(1, raw(amount=501))
    assert a != fingerprint(1, raw(transaction_date="2026-09-17"))
    assert a != fingerprint(1, raw(raw_description="TEA"))


def test_assign_occurrences_counts_repeats():
    assert assign_occurrences(["a", "b", "a", "a", "b"]) == [1, 1, 2, 3, 2]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_merchants_dedup.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`backend/finio/services/merchants.py`:
```python
import re
import sqlite3


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_merchant(raw: str | None, aliases: list[tuple[str, str]]) -> str:
    normalized = normalize_whitespace(raw)
    lowered = normalized.lower()
    for pattern, clean_name in aliases:
        if pattern.lower() in lowered:
            return clean_name
    return normalized


def load_aliases(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT pattern, clean_name FROM merchant_aliases ORDER BY id")
    return [(r["pattern"], r["clean_name"]) for r in rows]
```

`backend/finio/services/dedup.py`:
```python
import hashlib
from collections import Counter

from finio.importers.base import RawTransaction


def fingerprint(account_id: int, r: RawTransaction) -> str:
    parts = [
        str(account_id), r.transaction_date, r.posted_date or "",
        str(r.amount), r.raw_description,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def assign_occurrences(fps: list[str]) -> list[int]:
    seen: Counter[str] = Counter()
    out = []
    for fp in fps:
        seen[fp] += 1
        out.append(seen[fp])
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_merchants_dedup.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: merchant cleaning and dedup fingerprints" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Category rules engine

**Files:**
- Create: `backend/finio/services/rules.py`, `backend/tests/test_rules.py`

**Interfaces:**
- Produces:
  - `load_rules(conn) -> list[sqlite3.Row]` (ordered by `priority, id`)
  - `rule_matches(rule, merchant: str | None, description: str | None) -> bool`
  - `resolve_category(conn, rules, merchant, description, source_category) -> tuple[int, str]` returns `(category_id, category_source)` where source is `'rule'` or `'source_default'`; falls back to the `Other` category.
  - `reapply_rules(conn) -> int` re-evaluates every transaction whose `category_source != 'manual'` and returns how many were changed to a rule category.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_rules.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_rules.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`backend/finio/services/rules.py`:
```python
import sqlite3


def load_rules(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM category_rules ORDER BY priority, id").fetchall()


def rule_matches(rule, merchant: str | None, description: str | None) -> bool:
    field = merchant if rule["match_field"] == "merchant" else description
    haystack = (field or "").lower()
    pattern = rule["pattern"].lower()
    if rule["match_type"] == "equals":
        return haystack == pattern
    return pattern in haystack


def _other_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM categories WHERE name = 'Other'").fetchone()
    return row["id"] if row else conn.execute("SELECT MIN(id) AS id FROM categories").fetchone()["id"]


def resolve_category(
    conn: sqlite3.Connection,
    rules,
    merchant: str | None,
    description: str | None,
    source_category: str | None,
) -> tuple[int, str]:
    for rule in rules:
        if rule_matches(rule, merchant, description):
            return rule["category_id"], "rule"
    if source_category:
        row = conn.execute(
            "SELECT id FROM categories WHERE lower(name) = lower(?)", (source_category,)
        ).fetchone()
        if row:
            return row["id"], "source_default"
    return _other_id(conn), "source_default"


def reapply_rules(conn: sqlite3.Connection) -> int:
    rules = load_rules(conn)
    rows = conn.execute(
        "SELECT id, merchant_clean, raw_description, category_id, category_source "
        "FROM transactions WHERE category_source != 'manual'"
    ).fetchall()
    changed = 0
    with conn:
        for row in rows:
            for rule in rules:
                if rule_matches(rule, row["merchant_clean"], row["raw_description"]):
                    if row["category_id"] != rule["category_id"] or row["category_source"] != "rule":
                        conn.execute(
                            "UPDATE transactions SET category_id = ?, category_source = 'rule' WHERE id = ?",
                            (rule["category_id"], row["id"]),
                        )
                        changed += 1
                    break
    return changed
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_rules.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: category rules engine" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Ingestion service

**Files:**
- Create: `backend/finio/services/ingestion.py`, `backend/tests/test_ingestion.py`

**Interfaces:**
- Consumes: `AppleCardCsvImporter`, `RowError` (Task 2); `clean_merchant`, `load_aliases` (Task 3); `fingerprint`, `assign_occurrences` (Task 3); `load_rules`, `resolve_category` (Task 4); errors from `finio.errors` (Task 1).
- Produces: `IMPORTERS: dict[str, Importer]` keyed by account `source`; `ImportSummary(batch_id: int, rows_total: int, rows_added: int, rows_skipped: int, flagged: int, errors: list[RowError])`; `import_file(conn, account_id: int, filename: str, content: bytes) -> ImportSummary`. Raises `NotFoundError` (unknown account), `ValidationFailed` (source has no importer, or bad file), `ConflictError` (same file already imported for the account).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ingestion.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_ingestion.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`backend/finio/services/ingestion.py`:
```python
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from finio.errors import ConflictError, NotFoundError, ValidationFailed
from finio.importers.apple_card_csv import AppleCardCsvImporter
from finio.importers.base import RowError
from finio.services.dedup import assign_occurrences, fingerprint
from finio.services.merchants import clean_merchant, load_aliases
from finio.services.rules import load_rules, resolve_category

IMPORTERS = {"apple_card_csv": AppleCardCsvImporter()}


@dataclass
class ImportSummary:
    batch_id: int
    rows_total: int
    rows_added: int
    rows_skipped: int
    flagged: int
    errors: list[RowError] = field(default_factory=list)


def import_file(conn: sqlite3.Connection, account_id: int, filename: str, content: bytes) -> ImportSummary:
    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    importer = IMPORTERS.get(account["source"])
    if importer is None:
        raise ValidationFailed(f"Account '{account['name']}' has no file importer; add transactions manually")

    file_hash = hashlib.sha256(content).hexdigest()
    if conn.execute(
        "SELECT 1 FROM import_batches WHERE account_id = ? AND file_hash = ?", (account_id, file_hash)
    ).fetchone():
        raise ConflictError("This exact file was already imported for this account")

    try:
        result = importer.parse(content)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc

    aliases = load_aliases(conn)
    rules = load_rules(conn)
    fps = [fingerprint(account_id, r) for r in result.rows]
    occurrences = assign_occurrences(fps)

    added = skipped = 0
    with conn:
        batch_id = conn.execute(
            "INSERT INTO import_batches(account_id, filename, file_hash, imported_at) VALUES (?,?,?,?)",
            (account_id, filename, file_hash, datetime.now(UTC).isoformat()),
        ).lastrowid
        for raw, fp, occ in zip(result.rows, fps, occurrences):
            if conn.execute(
                "SELECT 1 FROM transactions WHERE fingerprint = ? AND occurrence = ?", (fp, occ)
            ).fetchone():
                skipped += 1
                continue
            merchant_clean = clean_merchant(raw.merchant_raw, aliases)
            category_id, category_source = resolve_category(
                conn, rules, merchant_clean, raw.raw_description, raw.source_category
            )
            conn.execute(
                "INSERT INTO transactions(account_id, batch_id, posted_date, transaction_date, amount, "
                "type, raw_description, merchant_raw, merchant_clean, cardholder, category_id, "
                "category_source, source_category, origin, fingerprint, occurrence, raw_row) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'import',?,?,?)",
                (account_id, batch_id, raw.posted_date, raw.transaction_date, raw.amount, raw.type,
                 raw.raw_description, raw.merchant_raw, merchant_clean, raw.cardholder, category_id,
                 category_source, raw.source_category, fp, occ, json.dumps(raw.raw_row)),
            )
            added += 1
        conn.execute(
            "UPDATE import_batches SET rows_total=?, rows_added=?, rows_skipped=? WHERE id=?",
            (len(result.rows), added, skipped, batch_id),
        )

    return ImportSummary(
        batch_id=batch_id,
        rows_total=len(result.rows),
        rows_added=added,
        rows_skipped=skipped,
        flagged=sum(1 for r in result.rows if r.flagged),
        errors=result.errors,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_ingestion.py -v`
Expected: 8 PASS. Then run the whole suite: `.venv/bin/pytest -q` (all green).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: ingestion service with dedup, rules, and batches" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: API app, accounts, categories, imports

**Files:**
- Create: `backend/finio/app.py`, `backend/finio/main.py`, `backend/finio/deps.py`, `backend/finio/api/__init__.py` (empty), `backend/finio/api/accounts.py`, `backend/finio/api/categories.py`, `backend/finio/api/imports.py`, `backend/tests/test_api_basics.py`

**Interfaces:**
- Consumes: `connect`, `init_db`, errors, `import_file`.
- Produces: `create_app(db_path=None) -> FastAPI` (path falls back to env `FINIO_DB`, then `data/finio.sqlite3`); `get_conn` dependency; all routes under `/api`; error handlers map `NotFoundError→404`, `ForbiddenError→403`, `ConflictError→409`, `ValidationFailed→400`, body `{"detail": str}`.
  - `GET /api/accounts` → `[{id,name,type,source,starting_balance,starting_balance_date}]`; `POST /api/accounts` body `{name, type, source, starting_balance=0, starting_balance_date=null}` → 201 row.
  - `GET /api/categories` → `[{id,name,parent_id}]`; `POST` `{name, parent_id?}` → 201; `PATCH /api/categories/{id}` `{name?, parent_id?}`; `DELETE /api/categories/{id}` → 204 (409 if in use by transactions or rules, or if name is `Other`).
  - `POST /api/imports` multipart `account_id` (int form field) + `file` → `{batch_id, rows_total, rows_added, rows_skipped, flagged, errors:[{line,message}]}`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_basics.py`:
```python
from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()


def make_acct(client, source="apple_card_csv", name="Apple Card", type_="credit_card"):
    r = client.post("/api/accounts", json={"name": name, "type": type_, "source": source})
    assert r.status_code == 201, r.text
    return r.json()


def test_accounts_create_and_list(client):
    made = make_acct(client)
    assert made["starting_balance"] == 0
    assert client.get("/api/accounts").json() == [made]


def test_account_validation(client):
    r = client.post("/api/accounts", json={"name": "X", "type": "bogus", "source": "manual"})
    assert r.status_code == 422


def test_categories_seeded_and_crud(client):
    cats = client.get("/api/categories").json()
    assert "Grocery" in [c["name"] for c in cats]
    created = client.post("/api/categories", json={"name": "Pets"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert client.patch(f"/api/categories/{cid}", json={"name": "Pet Care"}).json()["name"] == "Pet Care"
    assert client.post("/api/categories", json={"name": "Pet Care"}).status_code == 409
    assert client.delete(f"/api/categories/{cid}").status_code == 204


def test_cannot_delete_other_or_in_use_category(client):
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    assert client.delete(f"/api/categories/{cats['Other']}").status_code == 409
    acct = make_acct(client)
    client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert client.delete(f"/api/categories/{cats['Grocery']}").status_code == 409


def test_import_endpoint_and_error_mapping(client):
    acct = make_acct(client)
    r = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert r.status_code == 200
    body = r.json()
    assert (body["rows_added"], body["rows_skipped"], body["errors"]) == (6, 0, [])
    dup = client.post("/api/imports", data={"account_id": acct["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert dup.status_code == 409
    missing = client.post("/api/imports", data={"account_id": 999}, files={"file": ("a.csv", FIXTURE)})
    assert missing.status_code == 404
    manual = make_acct(client, source="manual", name="Bank", type_="checking")
    no_importer = client.post("/api/imports", data={"account_id": manual["id"]}, files={"file": ("a.csv", FIXTURE)})
    assert no_importer.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_api_basics.py -v`
Expected: FAIL (`ModuleNotFoundError: finio.app`).

- [ ] **Step 3: Implement app wiring**

`backend/finio/deps.py`:
```python
from fastapi import Request

from finio.db import connect


def get_conn(request: Request):
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
```

`backend/finio/app.py`:
```python
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from finio.db import connect, init_db
from finio.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed

STATUS = {NotFoundError: 404, ForbiddenError: 403, ConflictError: 409, ValidationFailed: 400}


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = Path(db_path or os.environ.get("FINIO_DB", "data/finio.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    init_db(conn)
    conn.close()

    app = FastAPI(title="Finio")
    app.state.db_path = path

    def make_handler(status: int):
        async def handler(request: Request, exc: Exception):
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        return handler

    for exc_type, status in STATUS.items():
        app.add_exception_handler(exc_type, make_handler(status))

    from finio.api import accounts, categories, imports

    for module in (accounts, categories, imports):
        app.include_router(module.router, prefix="/api")
    return app
```

`backend/finio/main.py`:
```python
from finio.app import create_app

app = create_app()
```

- [ ] **Step 4: Implement routers**

`backend/finio/api/accounts.py`:
```python
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finio.deps import get_conn

router = APIRouter()


class AccountIn(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["credit_card", "checking", "savings", "other"]
    source: Literal["apple_card_csv", "manual"]
    starting_balance: int = 0
    starting_balance_date: str | None = None


@router.get("/accounts")
def list_accounts(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY id")]


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        cur = conn.execute(
            "INSERT INTO accounts(name, type, source, starting_balance, starting_balance_date) "
            "VALUES (?,?,?,?,?)",
            (body.name.strip(), body.type, body.source, body.starting_balance, body.starting_balance_date),
        )
    return dict(conn.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone())
```

`backend/finio/api/categories.py`:
```python
import sqlite3

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from finio.deps import get_conn
from finio.errors import ConflictError, NotFoundError

router = APIRouter()


class CategoryIn(BaseModel):
    name: str = Field(min_length=1)
    parent_id: int | None = None


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    parent_id: int | None = None


def _get(conn, category_id: int):
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Category {category_id} not found")
    return row


@router.get("/categories")
def list_categories(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY name")]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, conn: sqlite3.Connection = Depends(get_conn)):
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO categories(name, parent_id) VALUES (?, ?)", (body.name.strip(), body.parent_id)
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("Category name already exists or parent is invalid") from exc
    return dict(_get(conn, cur.lastrowid))


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryPatch, conn: sqlite3.Connection = Depends(get_conn)):
    current = _get(conn, category_id)
    fields = body.model_dump(exclude_unset=True)
    name = (fields.get("name") or current["name"]).strip()
    parent = fields.get("parent_id", current["parent_id"])
    try:
        with conn:
            conn.execute("UPDATE categories SET name = ?, parent_id = ? WHERE id = ?", (name, parent, category_id))
    except sqlite3.IntegrityError as exc:
        raise ConflictError("Category name already exists or parent is invalid") from exc
    return dict(_get(conn, category_id))


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    row = _get(conn, category_id)
    if row["name"] == "Other":
        raise ConflictError("The 'Other' category cannot be deleted")
    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM transactions WHERE category_id = :i) + "
        "(SELECT COUNT(*) FROM category_rules WHERE category_id = :i) AS n", {"i": category_id},
    ).fetchone()["n"]
    if in_use:
        raise ConflictError("Category is used by transactions or rules; reassign them first")
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return Response(status_code=204)
```

`backend/finio/api/imports.py`:
```python
import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, UploadFile

from finio.deps import get_conn
from finio.services.ingestion import import_file

router = APIRouter()


@router.post("/imports")
async def upload_import(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    content = await file.read()
    summary = import_file(conn, account_id, file.filename or "upload.csv", content)
    return asdict(summary)
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat: FastAPI app with accounts, categories, imports" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Transaction listing, filters, cardholders, merchants

**Files:**
- Create: `backend/finio/services/filters.py`, `backend/finio/services/transactions.py`, `backend/finio/api/transactions.py`, `backend/tests/test_api_transactions.py`
- Modify: `backend/finio/app.py` (register router)

**Interfaces:**
- Produces:
  - `where_clause(*, date_from=None, date_to=None, account_id=None, cardholder=None, category_id=None, merchant=None, min_amount=None, max_amount=None, q=None) -> tuple[str, list]`. Returns a SQL fragment (never empty; `"1=1"` when no filters) and params. Assumes the transactions table is aliased `t`. Dates are ISO strings filtering `t.transaction_date`; `merchant` and `q` are case-insensitive substring matches (`q` searches `merchant_clean` and `raw_description`).
  - `TXN_SELECT: str` and `get_transaction(conn, id) -> dict` (raises `NotFoundError`); `list_transactions(conn, *, sort="date", order="desc", limit=50, offset=0, **filters) -> {"items": [...], "total": int}`.
  - Transaction dict keys: `id, account_id, account_name, transaction_date, posted_date, amount, type, merchant, description, cardholder, category_id, category, category_source, origin`.
  - `GET /api/transactions` query params: `date_from, date_to, account_id, cardholder, category_id, merchant, min_amount, max_amount, q, sort (date|amount|merchant), order (asc|desc), limit (1-500), offset`. `GET /api/cardholders` → `[str]` (distinct non-null). `GET /api/merchants` → `[str]` (distinct non-empty `merchant_clean`, sorted, max 500).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_transactions.py`:
```python
from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    other = make_account(source="manual", name="Bank", type="checking")
    ids = {
        "a": insert_txn(conn, acct, date="2026-09-01", amount=1000, merchant="Target", category="Grocery", cardholder="Ann"),
        "b": insert_txn(conn, acct, date="2026-09-05", amount=2500, merchant="Netflix", category="Entertainment", cardholder="Bob"),
        "c": insert_txn(conn, acct, date="2026-09-10", amount=-5000, type="payment", merchant="Payment", cardholder="Ann"),
        "d": insert_txn(conn, other, date="2026-08-20", amount=700, merchant="Corner Cafe", category="Restaurants",
                        description="CORNER CAFE SF", origin="manual", category_source="manual"),
    }
    return acct, other, ids


def get(client, **params):
    r = client.get("/api/transactions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_shape_and_default_sort(client, conn, make_account):
    _, _, ids = seed(conn, make_account)
    body = get(client)
    assert body["total"] == 4
    assert [t["id"] for t in body["items"]] == [ids["c"], ids["b"], ids["a"], ids["d"]]
    first = body["items"][0]
    assert first["merchant"] == "Payment" and first["category"] == "Other" and first["account_name"] == "Test Card"


def test_filters(client, conn, make_account):
    acct, other, ids = seed(conn, make_account)
    assert {t["id"] for t in get(client, date_from="2026-09-01", date_to="2026-09-05")["items"]} == {ids["a"], ids["b"]}
    assert [t["id"] for t in get(client, account_id=other)["items"]] == [ids["d"]]
    assert {t["id"] for t in get(client, cardholder="Ann")["items"]} == {ids["a"], ids["c"]}
    assert [t["id"] for t in get(client, merchant="netf")["items"]] == [ids["b"]]
    assert [t["id"] for t in get(client, q="corner cafe sf")["items"]] == [ids["d"]]
    assert {t["id"] for t in get(client, min_amount=1000, max_amount=2500)["items"]} == {ids["a"], ids["b"]}
    grocery = client.get("/api/categories").json()
    gid = next(c["id"] for c in grocery if c["name"] == "Grocery")
    assert [t["id"] for t in get(client, category_id=gid)["items"]] == [ids["a"]]


def test_sort_and_paging(client, conn, make_account):
    _, _, ids = seed(conn, make_account)
    by_amount = get(client, sort="amount", order="asc")
    assert [t["id"] for t in by_amount["items"]][0] == ids["c"]
    page = get(client, sort="date", order="asc", limit=2, offset=1)
    assert page["total"] == 4 and [t["id"] for t in page["items"]] == [ids["a"], ids["b"]]


def test_invalid_sort_rejected(client):
    assert client.get("/api/transactions", params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/transactions", params={"limit": 0}).status_code == 422


def test_cardholders_and_merchants(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/cardholders").json() == ["Ann", "Bob"]
    assert client.get("/api/merchants").json() == ["Corner Cafe", "Netflix", "Payment", "Target"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_api_transactions.py -v`
Expected: FAIL (404s / import errors).

- [ ] **Step 3: Implement filters and read services**

`backend/finio/services/filters.py`:
```python
def where_clause(
    *,
    date_from=None,
    date_to=None,
    account_id=None,
    cardholder=None,
    category_id=None,
    merchant=None,
    min_amount=None,
    max_amount=None,
    q=None,
) -> tuple[str, list]:
    conds: list[str] = []
    params: list = []

    def add(cond: str, *values):
        conds.append(cond)
        params.extend(values)

    if date_from:
        add("t.transaction_date >= ?", str(date_from))
    if date_to:
        add("t.transaction_date <= ?", str(date_to))
    if account_id is not None:
        add("t.account_id = ?", account_id)
    if cardholder:
        add("t.cardholder = ?", cardholder)
    if category_id is not None:
        add("t.category_id = ?", category_id)
    if merchant:
        add("lower(t.merchant_clean) LIKE ?", f"%{merchant.lower()}%")
    if min_amount is not None:
        add("t.amount >= ?", min_amount)
    if max_amount is not None:
        add("t.amount <= ?", max_amount)
    if q:
        like = f"%{q.lower()}%"
        add("(lower(t.merchant_clean) LIKE ? OR lower(t.raw_description) LIKE ?)", like, like)
    return (" AND ".join(conds) if conds else "1=1"), params
```

`backend/finio/services/transactions.py`:
```python
import sqlite3

from finio.errors import NotFoundError
from finio.services.filters import where_clause

TXN_SELECT = """
SELECT t.id, t.account_id, a.name AS account_name, t.transaction_date, t.posted_date, t.amount,
       t.type, t.merchant_clean AS merchant, t.raw_description AS description, t.cardholder,
       t.category_id, c.name AS category, t.category_source, t.origin
FROM transactions t
JOIN accounts a ON a.id = t.account_id
JOIN categories c ON c.id = t.category_id
"""

SORT_COLUMNS = {"date": "t.transaction_date", "amount": "t.amount", "merchant": "t.merchant_clean"}


def get_transaction(conn: sqlite3.Connection, transaction_id: int) -> dict:
    row = conn.execute(TXN_SELECT + " WHERE t.id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    return dict(row)


def list_transactions(
    conn: sqlite3.Connection, *, sort: str = "date", order: str = "desc",
    limit: int = 50, offset: int = 0, **filters,
) -> dict:
    where, params = where_clause(**filters)
    direction = "ASC" if order == "asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM transactions t WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"{TXN_SELECT} WHERE {where} ORDER BY {SORT_COLUMNS[sort]} {direction}, t.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total}
```

`backend/finio/api/transactions.py`:
```python
import datetime as dt
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query

from finio.deps import get_conn
from finio.services import transactions as svc

router = APIRouter()


@router.get("/transactions")
def list_transactions(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: int | None = None,
    cardholder: str | None = None,
    category_id: int | None = None,
    merchant: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    q: str | None = None,
    sort: Literal["date", "amount", "merchant"] = "date",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return svc.list_transactions(
        conn, sort=sort, order=order, limit=limit, offset=offset,
        date_from=date_from, date_to=date_to, account_id=account_id, cardholder=cardholder,
        category_id=category_id, merchant=merchant, min_amount=min_amount, max_amount=max_amount, q=q,
    )


@router.get("/cardholders")
def cardholders(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT DISTINCT cardholder FROM transactions WHERE cardholder IS NOT NULL AND cardholder != '' "
        "ORDER BY cardholder"
    )
    return [r["cardholder"] for r in rows]


@router.get("/merchants")
def merchants(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT DISTINCT merchant_clean FROM transactions WHERE merchant_clean IS NOT NULL "
        "AND merchant_clean != '' ORDER BY merchant_clean LIMIT 500"
    )
    return [r["merchant_clean"] for r in rows]
```

In `backend/finio/app.py`, change the router import/wiring to include the new module:
```python
    from finio.api import accounts, categories, imports, transactions

    for module in (accounts, categories, imports, transactions):
        app.include_router(module.router, prefix="/api")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: transaction listing with filters, cardholders, merchants" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Manual transactions (create, edit, delete, recategorize)

**Files:**
- Modify: `backend/finio/services/transactions.py`, `backend/finio/api/transactions.py`
- Test: `backend/tests/test_manual_transactions.py`

**Interfaces:**
- Consumes: `get_transaction`, `clean_merchant`, `load_aliases`, errors.
- Produces (service): `create_manual(conn, data: dict) -> dict`, `update_transaction(conn, transaction_id: int, fields: dict) -> dict`, `delete_transaction(conn, transaction_id: int) -> None`.
- Produces (API):
  - `POST /api/transactions` body `{account_id, date (YYYY-MM-DD), amount (int cents > 0), direction ("expense"|"income"|"refund"), merchant, description?, cardholder?, category_id}` → 201 transaction dict. Expense stores `+amount`, type `purchase`; income stores `-amount`, type `income`; refund stores `-amount`, type `refund`. Sets `origin='manual'`, `category_source='manual'`, `batch_id`/`fingerprint`/`raw_row` NULL, `posted_date = transaction_date`, `raw_description = description or merchant`.
  - `PATCH /api/transactions/{id}` body any subset of `{category_id, date, amount, direction, merchant, description, cardholder}`. Imported rows: only `category_id` allowed, otherwise 403. Setting `category_id` sets `category_source='manual'`. `amount` or `direction` may be sent alone (the other is derived from the stored row).
  - `DELETE /api/transactions/{id}` → 204; 403 for imported rows.
  - Unknown account → 404; unknown category → 400; blank merchant → 422; `amount <= 0` → 422.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_manual_transactions.py`:
```python
from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()


def cat(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def manual_account(client):
    return client.post("/api/accounts", json={"name": "Chase", "type": "checking", "source": "manual"}).json()["id"]


def create(client, acct, **over):
    body = dict(account_id=acct, date="2026-09-10", amount=4250, direction="expense",
                merchant="  Corner   Cafe ", category_id=cat(client, "Restaurants"))
    body.update(over)
    return client.post("/api/transactions", json=body)


def test_create_expense(client):
    acct = manual_account(client)
    r = create(client, acct, description="Lunch", cardholder="Ann")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["amount"] == 4250 and t["type"] == "purchase"
    assert t["merchant"] == "Corner Cafe" and t["description"] == "Lunch"
    assert t["origin"] == "manual" and t["category_source"] == "manual" and t["category"] == "Restaurants"
    assert t["transaction_date"] == "2026-09-10" and t["cardholder"] == "Ann"


def test_income_and_refund_are_negative(client):
    acct = manual_account(client)
    inc = create(client, acct, direction="income", merchant="Employer", category_id=cat(client, "Other")).json()
    ref = create(client, acct, direction="refund").json()
    assert (inc["amount"], inc["type"]) == (-4250, "income")
    assert (ref["amount"], ref["type"]) == (-4250, "refund")


def test_description_defaults_to_merchant(client):
    acct = manual_account(client)
    assert create(client, acct).json()["description"] == "Corner Cafe"


def test_alias_applied_to_manual_merchant(client, conn):
    acct = manual_account(client)
    conn.execute("INSERT INTO merchant_aliases(pattern, clean_name) VALUES ('corner cafe', 'Corner Café')")
    conn.commit()
    assert create(client, acct).json()["merchant"] == "Corner Café"


def test_create_validation(client):
    acct = manual_account(client)
    assert create(client, acct, amount=0).status_code == 422
    assert create(client, acct, amount=-5).status_code == 422
    assert create(client, acct, merchant="   ").status_code == 422
    assert create(client, acct, date="not-a-date").status_code == 422
    assert create(client, acct, direction="gift").status_code == 422
    assert create(client, 999).status_code == 404
    assert create(client, acct, category_id=9999).status_code == 400


def test_edit_manual_fields(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    r = client.patch(f"/api/transactions/{tid}", json={
        "amount": 1000, "merchant": "New Place", "date": "2026-09-11",
        "description": "Edited", "cardholder": "Bob", "category_id": cat(client, "Shopping"),
    })
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["amount"], t["merchant"], t["transaction_date"]) == (1000, "New Place", "2026-09-11")
    assert (t["description"], t["cardholder"], t["category"]) == ("Edited", "Bob", "Shopping")


def test_edit_direction_alone_flips_sign_and_amount_alone_keeps_sign(client):
    acct = manual_account(client)
    tid = create(client, acct, direction="income").json()["id"]
    t = client.patch(f"/api/transactions/{tid}", json={"amount": 999}).json()
    assert (t["amount"], t["type"]) == (-999, "income")
    t = client.patch(f"/api/transactions/{tid}", json={"direction": "expense"}).json()
    assert (t["amount"], t["type"]) == (999, "purchase")


def test_edit_validation(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    assert client.patch(f"/api/transactions/{tid}", json={"amount": 0}).status_code == 422
    assert client.patch(f"/api/transactions/{tid}", json={"category_id": 9999}).status_code == 400
    assert client.patch("/api/transactions/9999", json={"merchant": "X"}).status_code == 404


def test_imported_rows_only_recategorizable_and_not_deletable(client):
    apple = client.post("/api/accounts", json={"name": "Apple", "type": "credit_card", "source": "apple_card_csv"}).json()
    client.post("/api/imports", data={"account_id": apple["id"]}, files={"file": ("a.csv", FIXTURE)})
    row = client.get("/api/transactions", params={"merchant": "target"}).json()["items"][0]
    assert client.patch(f"/api/transactions/{row['id']}", json={"amount": 1}).status_code == 403
    assert client.patch(f"/api/transactions/{row['id']}", json={"merchant": "X"}).status_code == 403
    ok = client.patch(f"/api/transactions/{row['id']}", json={"category_id": cat(client, "Shopping")})
    assert ok.status_code == 200
    assert ok.json()["category"] == "Shopping" and ok.json()["category_source"] == "manual"
    assert client.delete(f"/api/transactions/{row['id']}").status_code == 403


def test_delete_manual(client):
    acct = manual_account(client)
    tid = create(client, acct).json()["id"]
    assert client.delete(f"/api/transactions/{tid}").status_code == 204
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.delete(f"/api/transactions/{tid}").status_code == 404


def test_manual_category_survives_rule_reapply(client, conn):
    from finio.services.rules import reapply_rules

    acct = manual_account(client)
    tid = create(client, acct, merchant="Target Run", category_id=cat(client, "Shopping")).json()["id"]
    conn.execute(
        "INSERT INTO category_rules(match_field, match_type, pattern, category_id) VALUES ('merchant','contains','target',?)",
        (cat(client, "Grocery"),),
    )
    conn.commit()
    reapply_rules(conn)
    assert client.get("/api/transactions").json()["items"][0]["category"] == "Shopping"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_manual_transactions.py -v`
Expected: FAIL (405/404 — routes missing).

- [ ] **Step 3: Extend the service**

Append to `backend/finio/services/transactions.py` (add the new imports at the top of the file):
```python
from finio.errors import ForbiddenError, ValidationFailed
from finio.services.merchants import clean_merchant, load_aliases, normalize_whitespace

DIRECTION_TO_TYPE = {"expense": "purchase", "income": "income", "refund": "refund"}
TYPE_TO_DIRECTION = {v: k for k, v in DIRECTION_TO_TYPE.items()}


def _signed(direction: str, amount: int) -> int:
    return abs(amount) if direction == "expense" else -abs(amount)


def _require_category(conn: sqlite3.Connection, category_id: int) -> None:
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise ValidationFailed(f"Category {category_id} does not exist")


def create_manual(conn: sqlite3.Connection, data: dict) -> dict:
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (data["account_id"],)).fetchone() is None:
        raise NotFoundError(f"Account {data['account_id']} not found")
    _require_category(conn, data["category_id"])
    merchant = normalize_whitespace(data["merchant"])
    date = str(data["date"])
    with conn:
        cur = conn.execute(
            "INSERT INTO transactions(account_id, posted_date, transaction_date, amount, type, "
            "raw_description, merchant_raw, merchant_clean, cardholder, category_id, category_source, origin) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'manual','manual')",
            (data["account_id"], date, date, _signed(data["direction"], data["amount"]),
             DIRECTION_TO_TYPE[data["direction"]], data.get("description") or merchant, merchant,
             clean_merchant(merchant, load_aliases(conn)), data.get("cardholder") or None, data["category_id"]),
        )
    return get_transaction(conn, cur.lastrowid)


def update_transaction(conn: sqlite3.Connection, transaction_id: int, fields: dict) -> dict:
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    if row["origin"] == "import" and set(fields) - {"category_id"}:
        raise ForbiddenError("Imported transactions can only be recategorized")
    if "category_id" in fields:
        if fields["category_id"] is None:
            raise ValidationFailed("category_id cannot be null")
        _require_category(conn, fields["category_id"])

    sets: dict = {}
    if "category_id" in fields:
        sets["category_id"] = fields["category_id"]
        sets["category_source"] = "manual"
    if row["origin"] == "manual":
        if "merchant" in fields:
            merchant = normalize_whitespace(fields["merchant"])
            sets["merchant_raw"] = merchant
            sets["merchant_clean"] = clean_merchant(merchant, load_aliases(conn))
        if "description" in fields:
            sets["raw_description"] = fields["description"] or sets.get("merchant_raw") or row["merchant_raw"]
        if "date" in fields:
            sets["transaction_date"] = sets["posted_date"] = str(fields["date"])
        if "cardholder" in fields:
            sets["cardholder"] = fields["cardholder"] or None
        if "amount" in fields or "direction" in fields:
            direction = fields.get("direction") or TYPE_TO_DIRECTION.get(row["type"], "expense")
            amount = fields.get("amount", abs(row["amount"]))
            sets["amount"] = _signed(direction, amount)
            sets["type"] = DIRECTION_TO_TYPE[direction]
    if sets:
        assignments = ", ".join(f"{col} = ?" for col in sets)
        with conn:
            conn.execute(f"UPDATE transactions SET {assignments} WHERE id = ?", [*sets.values(), transaction_id])
    return get_transaction(conn, transaction_id)


def delete_transaction(conn: sqlite3.Connection, transaction_id: int) -> None:
    row = conn.execute("SELECT origin FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    if row["origin"] == "import":
        raise ForbiddenError("Imported transactions cannot be deleted")
    with conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
```

- [ ] **Step 4: Extend the API**

In `backend/finio/api/transactions.py`, update the imports and append the models and routes:
```python
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
```
```python
class ManualTransactionIn(BaseModel):
    account_id: int
    date: dt.date
    amount: int = Field(gt=0)
    direction: Literal["expense", "income", "refund"]
    merchant: str
    description: str | None = None
    cardholder: str | None = None
    category_id: int

    @field_validator("merchant")
    @classmethod
    def merchant_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("merchant is required")
        return v


class TransactionPatch(BaseModel):
    category_id: int | None = None
    date: dt.date | None = None
    amount: int | None = Field(default=None, gt=0)
    direction: Literal["expense", "income", "refund"] | None = None
    merchant: str | None = None
    description: str | None = None
    cardholder: str | None = None

    @field_validator("merchant")
    @classmethod
    def merchant_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("merchant cannot be blank")
        return v


@router.post("/transactions", status_code=201)
def create_transaction(body: ManualTransactionIn, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.create_manual(conn, body.model_dump())


@router.patch("/transactions/{transaction_id}")
def update_transaction(transaction_id: int, body: TransactionPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.update_transaction(conn, transaction_id, body.model_dump(exclude_unset=True))


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    svc.delete_transaction(conn, transaction_id)
    return Response(status_code=204)
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat: manual transaction entry, edit, delete, recategorize" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Rules and merchant alias API

**Files:**
- Create: `backend/finio/api/rules.py`, `backend/tests/test_api_rules.py`
- Modify: `backend/finio/app.py` (register router)

**Interfaces:**
- Consumes: `reapply_rules` (Task 4).
- Produces:
  - `GET /api/rules` → `[{id, match_field, match_type, pattern, category_id, priority}]` ordered by `priority, id`; `POST /api/rules` body `{match_field ("merchant"|"description"), match_type ("contains"|"equals"), pattern (non-blank), category_id, priority=100}` → 201 (unknown category → 400); `PATCH /api/rules/{id}` (any subset); `DELETE /api/rules/{id}` → 204; `POST /api/rules/reapply` → `{"updated": int}`.
  - `GET /api/aliases` → `[{id, pattern, clean_name}]`; `POST /api/aliases` `{pattern, clean_name}` → 201; `DELETE /api/aliases/{id}` → 204.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_rules.py`:
```python
from tests.helpers import insert_txn


def cat(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def rule_body(client, **over):
    body = dict(match_field="merchant", match_type="contains", pattern="target", category_id=cat(client, "Grocery"))
    body.update(over)
    return body


def test_rule_crud(client):
    r = client.post("/api/rules", json=rule_body(client))
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["priority"] == 100
    assert client.get("/api/rules").json() == [rule]
    patched = client.patch(f"/api/rules/{rule['id']}", json={"pattern": "target store", "priority": 5}).json()
    assert (patched["pattern"], patched["priority"]) == ("target store", 5)
    assert client.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert client.get("/api/rules").json() == []


def test_rule_validation(client):
    assert client.post("/api/rules", json=rule_body(client, pattern="  ")).status_code == 422
    assert client.post("/api/rules", json=rule_body(client, match_field="amount")).status_code == 422
    assert client.post("/api/rules", json=rule_body(client, category_id=9999)).status_code == 400
    assert client.patch("/api/rules/999", json={"pattern": "x"}).status_code == 404
    assert client.delete("/api/rules/999").status_code == 404


def test_reapply(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Target Store", category="Other")
    client.post("/api/rules", json=rule_body(client))
    assert client.post("/api/rules/reapply").json() == {"updated": 1}
    assert client.get("/api/transactions").json()["items"][0]["category"] == "Grocery"
    assert client.post("/api/rules/reapply").json() == {"updated": 0}


def test_alias_crud(client):
    r = client.post("/api/aliases", json={"pattern": "sq *", "clean_name": "Square Vendor"})
    assert r.status_code == 201
    alias = r.json()
    assert client.get("/api/aliases").json() == [alias]
    assert client.post("/api/aliases", json={"pattern": " ", "clean_name": "X"}).status_code == 422
    assert client.delete(f"/api/aliases/{alias['id']}").status_code == 204
    assert client.delete(f"/api/aliases/{alias['id']}").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_api_rules.py -v`
Expected: FAIL (404s).

- [ ] **Step 3: Implement**

`backend/finio/api/rules.py`:
```python
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator

from finio.deps import get_conn
from finio.errors import NotFoundError, ValidationFailed
from finio.services.rules import reapply_rules

router = APIRouter()


def _not_blank(v: str | None) -> str | None:
    if v is not None and not v.strip():
        raise ValueError("must not be blank")
    return v.strip() if v is not None else v


class RuleIn(BaseModel):
    match_field: Literal["merchant", "description"]
    match_type: Literal["contains", "equals"]
    pattern: str
    category_id: int
    priority: int = 100

    _check_pattern = field_validator("pattern")(_not_blank)


class RulePatch(BaseModel):
    match_field: Literal["merchant", "description"] | None = None
    match_type: Literal["contains", "equals"] | None = None
    pattern: str | None = None
    category_id: int | None = None
    priority: int | None = None

    _check_pattern = field_validator("pattern")(_not_blank)


class AliasIn(BaseModel):
    pattern: str
    clean_name: str

    _check_pattern = field_validator("pattern")(_not_blank)
    _check_name = field_validator("clean_name")(_not_blank)


def _require_category(conn, category_id: int) -> None:
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise ValidationFailed(f"Category {category_id} does not exist")


def _get_rule(conn, rule_id: int) -> dict:
    row = conn.execute("SELECT * FROM category_rules WHERE id = ?", (rule_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Rule {rule_id} not found")
    return dict(row)


@router.get("/rules")
def list_rules(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM category_rules ORDER BY priority, id")]


@router.post("/rules/reapply")
def reapply(conn: sqlite3.Connection = Depends(get_conn)):
    return {"updated": reapply_rules(conn)}


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, conn: sqlite3.Connection = Depends(get_conn)):
    _require_category(conn, body.category_id)
    with conn:
        cur = conn.execute(
            "INSERT INTO category_rules(match_field, match_type, pattern, category_id, priority) VALUES (?,?,?,?,?)",
            (body.match_field, body.match_type, body.pattern, body.category_id, body.priority),
        )
    return _get_rule(conn, cur.lastrowid)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RulePatch, conn: sqlite3.Connection = Depends(get_conn)):
    current = _get_rule(conn, rule_id)
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "category_id" in fields:
        _require_category(conn, fields["category_id"])
    merged = {**current, **fields}
    with conn:
        conn.execute(
            "UPDATE category_rules SET match_field=?, match_type=?, pattern=?, category_id=?, priority=? WHERE id=?",
            (merged["match_field"], merged["match_type"], merged["pattern"], merged["category_id"],
             merged["priority"], rule_id),
        )
    return _get_rule(conn, rule_id)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    _get_rule(conn, rule_id)
    with conn:
        conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
    return Response(status_code=204)


@router.get("/aliases")
def list_aliases(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM merchant_aliases ORDER BY id")]


@router.post("/aliases", status_code=201)
def create_alias(body: AliasIn, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        cur = conn.execute(
            "INSERT INTO merchant_aliases(pattern, clean_name) VALUES (?, ?)", (body.pattern, body.clean_name)
        )
    return dict(conn.execute("SELECT * FROM merchant_aliases WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    if conn.execute("SELECT 1 FROM merchant_aliases WHERE id = ?", (alias_id,)).fetchone() is None:
        raise NotFoundError(f"Alias {alias_id} not found")
    with conn:
        conn.execute("DELETE FROM merchant_aliases WHERE id = ?", (alias_id,))
    return Response(status_code=204)
```

In `backend/finio/app.py` extend the wiring:
```python
    from finio.api import accounts, categories, imports, rules, transactions

    for module in (accounts, categories, imports, transactions, rules):
        app.include_router(module.router, prefix="/api")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: rules and merchant alias API" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Spending analytics (by category, trends, top merchants)

**Files:**
- Create: `backend/finio/services/analytics.py`, `backend/finio/api/analytics.py`, `backend/tests/test_api_analytics.py`
- Modify: `backend/finio/app.py` (register router)

**Interfaces:**
- Consumes: `where_clause` (Task 7).
- Produces: `spending_by_category(conn, **filters) -> [{category_id, category, total, count}]` (total desc), `spending_trends(conn, **filters) -> [{month: "YYYY-MM", total}]` (month asc; months with no spending are omitted), `top_merchants(conn, limit=10, **filters) -> [{merchant, total, count}]` (total desc). All count only `type = 'purchase'`. Filters accepted: `date_from, date_to, account_id, cardholder, category_id` (the last is useful for trends).
- API: `GET /api/analytics/spending-by-category`, `/api/analytics/trends`, `/api/analytics/top-merchants` (extra param `limit` 1-100, default 10). Common query params: `date_from, date_to, account_id, cardholder, category_id`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_analytics.py`:
```python
from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=1000, merchant="Target", category="Grocery", cardholder="Ann")
    insert_txn(conn, acct, date="2026-09-02", amount=2000, merchant="Target", category="Grocery", cardholder="Bob")
    insert_txn(conn, acct, date="2026-09-03", amount=500, merchant="Netflix", category="Entertainment", cardholder="Ann")
    insert_txn(conn, acct, date="2026-09-04", amount=-9999, type="payment", merchant="Payment", category="Other")
    insert_txn(conn, acct, date="2026-09-05", amount=-300, type="refund", merchant="Target", category="Grocery")
    return acct


def test_spending_by_category_excludes_payments_and_refunds(client, conn, make_account):
    seed(conn, make_account)
    data = client.get("/api/analytics/spending-by-category").json()
    assert data == [
        {"category_id": data[0]["category_id"], "category": "Grocery", "total": 3000, "count": 2},
        {"category_id": data[1]["category_id"], "category": "Entertainment", "total": 500, "count": 1},
    ]


def test_filters_apply(client, conn, make_account):
    seed(conn, make_account)
    data = client.get("/api/analytics/spending-by-category", params={"cardholder": "Ann"}).json()
    assert {(d["category"], d["total"]) for d in data} == {("Grocery", 1000), ("Entertainment", 500)}
    data = client.get("/api/analytics/spending-by-category", params={"date_from": "2026-09-01"}).json()
    assert {(d["category"], d["total"]) for d in data} == {("Grocery", 2000), ("Entertainment", 500)}


def test_trends_by_month(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/analytics/trends").json() == [
        {"month": "2026-08", "total": 1000},
        {"month": "2026-09", "total": 2500},
    ]


def test_trends_for_one_category(client, conn, make_account):
    seed(conn, make_account)
    grocery = next(c["id"] for c in client.get("/api/categories").json() if c["name"] == "Grocery")
    data = client.get("/api/analytics/trends", params={"category_id": grocery}).json()
    assert data == [{"month": "2026-08", "total": 1000}, {"month": "2026-09", "total": 2000}]


def test_top_merchants(client, conn, make_account):
    seed(conn, make_account)
    assert client.get("/api/analytics/top-merchants").json() == [
        {"merchant": "Target", "total": 3000, "count": 2},
        {"merchant": "Netflix", "total": 500, "count": 1},
    ]
    one = client.get("/api/analytics/top-merchants", params={"limit": 1}).json()
    assert len(one) == 1 and one[0]["merchant"] == "Target"
    assert client.get("/api/analytics/top-merchants", params={"limit": 0}).status_code == 422


def test_empty_database(client):
    assert client.get("/api/analytics/spending-by-category").json() == []
    assert client.get("/api/analytics/trends").json() == []
    assert client.get("/api/analytics/top-merchants").json() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_api_analytics.py -v`
Expected: FAIL (404s).

- [ ] **Step 3: Implement**

`backend/finio/services/analytics.py`:
```python
import sqlite3

from finio.services.filters import where_clause


def _spending_where(**filters) -> tuple[str, list]:
    where, params = where_clause(**filters)
    return f"t.type = 'purchase' AND {where}", params


def spending_by_category(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT c.id AS category_id, c.name AS category, SUM(t.amount) AS total, COUNT(*) AS count "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id WHERE {where} "
        "GROUP BY c.id ORDER BY total DESC, c.name",
        params,
    )
    return [dict(r) for r in rows]


def spending_trends(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT strftime('%Y-%m', t.transaction_date) AS month, SUM(t.amount) AS total "
        f"FROM transactions t WHERE {where} GROUP BY month ORDER BY month",
        params,
    )
    return [dict(r) for r in rows]


def top_merchants(conn: sqlite3.Connection, limit: int = 10, **filters) -> list[dict]:
    where, params = _spending_where(**filters)
    rows = conn.execute(
        "SELECT t.merchant_clean AS merchant, SUM(t.amount) AS total, COUNT(*) AS count "
        f"FROM transactions t WHERE {where} AND t.merchant_clean != '' "
        "GROUP BY t.merchant_clean ORDER BY total DESC, merchant LIMIT ?",
        [*params, limit],
    )
    return [dict(r) for r in rows]
```

`backend/finio/api/analytics.py`:
```python
import datetime as dt
import sqlite3

from fastapi import APIRouter, Depends, Query

from finio.deps import get_conn
from finio.services import analytics as svc

router = APIRouter(prefix="/analytics")


def common_filters(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: int | None = None,
    cardholder: str | None = None,
    category_id: int | None = None,
) -> dict:
    return dict(
        date_from=date_from, date_to=date_to, account_id=account_id,
        cardholder=cardholder, category_id=category_id,
    )


@router.get("/spending-by-category")
def spending_by_category(filters: dict = Depends(common_filters), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.spending_by_category(conn, **filters)


@router.get("/trends")
def trends(filters: dict = Depends(common_filters), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.spending_trends(conn, **filters)


@router.get("/top-merchants")
def top_merchants(
    limit: int = Query(10, ge=1, le=100),
    filters: dict = Depends(common_filters),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return svc.top_merchants(conn, limit=limit, **filters)
```

In `backend/finio/app.py` extend the wiring:
```python
    from finio.api import accounts, analytics, categories, imports, rules, transactions

    for module in (accounts, categories, imports, transactions, rules, analytics):
        app.include_router(module.router, prefix="/api")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: spending analytics endpoints" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Recurring-charge detection

**Files:**
- Create: `backend/finio/services/recurring.py`, `backend/tests/test_recurring.py`
- Modify: `backend/finio/api/analytics.py` (add `/recurring`)

**Interfaces:**
- Consumes: `where_clause` (Task 7).
- Produces:
  - `detect(merchant: str, txns: list[tuple[str, int]]) -> dict | None` where `txns` are `(iso_date, amount_cents)`. Returns `{merchant, cadence ("weekly"|"biweekly"|"monthly"|"yearly"), typical_amount, count, last_date, next_expected}` or `None`. Rules: at least 3 distinct dates; every gap between consecutive distinct dates within the cadence tolerance of the median gap; amounts within 25% of the median (`(max - min) / median <= 0.25`).
  - `find_recurring(conn, **filters) -> list[dict]` (typical_amount desc), purchases only.
  - `GET /api/analytics/recurring` (same common filters).
- Cadence table (center days, tolerance days): weekly (7, 2), biweekly (14, 3), monthly (30, 5), yearly (365, 10).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_recurring.py`:
```python
from finio.services.recurring import detect
from tests.helpers import insert_txn


def test_monthly_detected():
    r = detect("Netflix", [("2026-07-15", 1549), ("2026-08-15", 1549), ("2026-09-14", 1549)])
    assert r == {
        "merchant": "Netflix", "cadence": "monthly", "typical_amount": 1549, "count": 3,
        "last_date": "2026-09-14", "next_expected": "2026-10-14",
    }


def test_monthly_with_short_and_long_months():
    dates = ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    assert detect("Rent Co", [(d, 100000) for d in dates])["cadence"] == "monthly"


def test_weekly_and_biweekly():
    weekly = [(f"2026-09-{d:02d}", 500) for d in (1, 8, 15, 22)]
    assert detect("Gym", weekly)["cadence"] == "weekly"
    biweekly = [("2026-08-01", 900), ("2026-08-15", 900), ("2026-08-29", 900)]
    assert detect("Payroll Fee", biweekly)["cadence"] == "biweekly"


def test_yearly():
    r = detect("Insurance", [("2024-03-01", 90000), ("2025-03-02", 90000), ("2026-03-01", 90000)])
    assert r["cadence"] == "yearly"


def test_too_few_occurrences():
    assert detect("X", [("2026-08-01", 500), ("2026-09-01", 500)]) is None


def test_same_day_duplicates_do_not_count_as_extra_occurrences():
    assert detect("X", [("2026-08-01", 500), ("2026-08-01", 500), ("2026-09-01", 500)]) is None


def test_irregular_gaps_rejected():
    assert detect("Grocer", [("2026-09-01", 500), ("2026-09-04", 500), ("2026-09-20", 500)]) is None


def test_wildly_varying_amounts_rejected():
    assert detect("Shop", [("2026-07-01", 500), ("2026-08-01", 5000), ("2026-09-01", 900)]) is None


def test_slightly_varying_amounts_accepted():
    r = detect("Utility", [("2026-07-01", 8000), ("2026-08-01", 9000), ("2026-09-01", 8500)])
    assert r is not None and r["typical_amount"] == 8500


def test_endpoint_groups_by_merchant_and_ignores_non_purchases(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, date=d, amount=1549, merchant="Netflix", category="Entertainment")
    for d in ("2026-07-01", "2026-08-01", "2026-09-01"):
        insert_txn(conn, acct, date=d, amount=-5000, type="payment", merchant="Payment")
    insert_txn(conn, acct, date="2026-09-02", amount=700, merchant="One Off")
    data = client.get("/api/analytics/recurring").json()
    assert [d["merchant"] for d in data] == ["Netflix"]
    assert data[0]["cadence"] == "monthly"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_recurring.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`backend/finio/services/recurring.py`:
```python
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta

from finio.services.filters import where_clause

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.25
CADENCES = [("weekly", 7, 2), ("biweekly", 14, 3), ("monthly", 30, 5), ("yearly", 365, 10)]


def detect(merchant: str, txns: list[tuple[str, int]]) -> dict | None:
    dates = sorted({date.fromisoformat(d) for d, _ in txns})
    if len(dates) < MIN_OCCURRENCES:
        return None

    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    median_gap = statistics.median(gaps)
    cadence = next(
        (
            name
            for name, center, tol in CADENCES
            if abs(median_gap - center) <= tol and all(abs(g - median_gap) <= tol for g in gaps)
        ),
        None,
    )
    if cadence is None:
        return None

    amounts = [a for _, a in txns]
    typical = int(statistics.median(amounts))
    if typical <= 0 or (max(amounts) - min(amounts)) / typical > AMOUNT_TOLERANCE:
        return None

    last = dates[-1]
    return {
        "merchant": merchant,
        "cadence": cadence,
        "typical_amount": typical,
        "count": len(dates),
        "last_date": last.isoformat(),
        "next_expected": (last + timedelta(days=round(median_gap))).isoformat(),
    }


def find_recurring(conn: sqlite3.Connection, **filters) -> list[dict]:
    where, params = where_clause(**filters)
    rows = conn.execute(
        "SELECT t.merchant_clean AS merchant, t.transaction_date AS d, t.amount AS amount "
        f"FROM transactions t WHERE t.type = 'purchase' AND t.merchant_clean != '' AND {where}",
        params,
    )
    grouped: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in rows:
        grouped[r["merchant"]].append((r["d"], r["amount"]))
    found = [hit for m, txns in grouped.items() if (hit := detect(m, txns))]
    return sorted(found, key=lambda h: (-h["typical_amount"], h["merchant"]))
```

Append to `backend/finio/api/analytics.py`:
```python
from finio.services.recurring import find_recurring


@router.get("/recurring")
def recurring(filters: dict = Depends(common_filters), conn: sqlite3.Connection = Depends(get_conn)):
    return find_recurring(conn, **filters)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (backend complete).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: recurring charge detection" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: Frontend scaffold and tested helpers

**Files:**
- Create: `frontend/` (Vite React-TS app), `frontend/src/lib/money.ts`, `frontend/src/lib/query.ts`, `frontend/src/lib/useFetch.ts`, `frontend/src/lib/money.test.ts`, `frontend/src/lib/query.test.ts`
- Modify: `frontend/vite.config.ts`, `frontend/package.json` (test script)

**Interfaces:**
- Produces:
  - `formatCents(cents: number): string` → `"$1,234.56"` / `"-$5.00"`.
  - `parseAmountToCents(input: string): number | null` → accepts `"12"`, `"12.5"`, `"$1,234.56"`; returns `null` for empty, non-numeric, more than 2 decimals, or zero.
  - `toQueryString(params: Record<string, string | number | null | undefined>): string` → `""` when nothing set, otherwise `"?a=1&b=x"`; skips `undefined`, `null`, and `""`.
  - `useFetch<T>(fn: () => Promise<T>, deps: unknown[]) -> { data: T | null, error: string | null, loading: boolean, reload: () => void }`.
- Dev server on `:5173` proxies `/api` to `http://127.0.0.1:8000`.

- [ ] **Step 1: Scaffold and install**

Run:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install && npm install react-router-dom recharts && npm install -D vitest
```
Then delete the template demo files: `rm -f src/App.css src/assets/react.svg public/vite.svg` and replace `src/index.css` usage later (Task 13 writes `styles.css`). Expected: `npm install` finishes without errors. If a peer-dependency error appears for `recharts`, rerun with `--legacy-peer-deps` and note it in the README.

- [ ] **Step 2: Configure Vite proxy and Vitest**

Replace `frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'node' },
})
```
In `frontend/package.json` add to `"scripts"`: `"test": "vitest run"`.

- [ ] **Step 3: Write the failing tests**

`frontend/src/lib/money.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { formatCents, parseAmountToCents } from './money'

describe('formatCents', () => {
  it('formats dollars and cents', () => {
    expect(formatCents(123456)).toBe('$1,234.56')
    expect(formatCents(5)).toBe('$0.05')
    expect(formatCents(0)).toBe('$0.00')
  })
  it('formats negatives', () => {
    expect(formatCents(-500)).toBe('-$5.00')
  })
})

describe('parseAmountToCents', () => {
  it('parses plain and formatted amounts', () => {
    expect(parseAmountToCents('12')).toBe(1200)
    expect(parseAmountToCents('12.5')).toBe(1250)
    expect(parseAmountToCents('$1,234.56')).toBe(123456)
    expect(parseAmountToCents(' 0.07 ')).toBe(7)
  })
  it('rejects invalid input', () => {
    expect(parseAmountToCents('')).toBeNull()
    expect(parseAmountToCents('abc')).toBeNull()
    expect(parseAmountToCents('1.234')).toBeNull()
    expect(parseAmountToCents('-5')).toBeNull()
    expect(parseAmountToCents('0')).toBeNull()
    expect(parseAmountToCents('0.00')).toBeNull()
  })
})
```

`frontend/src/lib/query.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { toQueryString } from './query'

describe('toQueryString', () => {
  it('returns empty string when nothing is set', () => {
    expect(toQueryString({})).toBe('')
    expect(toQueryString({ a: undefined, b: null, c: '' })).toBe('')
  })
  it('encodes set values', () => {
    expect(toQueryString({ q: 'a b', limit: 50, skip: undefined })).toBe('?q=a+b&limit=50')
  })
  it('keeps zero', () => {
    expect(toQueryString({ offset: 0 })).toBe('?offset=0')
  })
})
```

- [ ] **Step 4: Run to verify failure**

Run: `cd frontend && npm test`
Expected: FAIL (cannot resolve `./money`, `./query`).

- [ ] **Step 5: Implement**

`frontend/src/lib/money.ts`:
```ts
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatCents(cents: number): string {
  return usd.format(cents / 100)
}

export function parseAmountToCents(input: string): number | null {
  const cleaned = input.trim().replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const [dollars, fraction = ''] = cleaned.split('.')
  const cents = parseInt(dollars, 10) * 100 + parseInt(fraction.padEnd(2, '0') || '0', 10)
  return cents > 0 ? cents : null
}
```

`frontend/src/lib/query.ts`:
```ts
export function toQueryString(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
```

`frontend/src/lib/useFetch.ts`:
```ts
import { useCallback, useEffect, useState } from 'react'

export function useFetch<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fn()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload }
}
```

- [ ] **Step 6: Run to verify pass**

Run: `cd frontend && npm test`
Expected: 8 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: frontend scaffold with money and query helpers" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 13: API client, app shell, Accounts and Import screens

**Files:**
- Create: `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/components/FilterBar.tsx`, `frontend/src/pages/Accounts.tsx`, `frontend/src/pages/Import.tsx`
- Modify: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/index.html` (title `Finio`)

**Interfaces:**
- Produces (`api.ts`): types `Account`, `Category`, `Transaction`, `TransactionPage`, `Filters`, `Rule`, `ImportSummary`, `CategoryTotal`, `MonthTotal`, `MerchantTotal`, `RecurringCharge`, `ManualTransactionInput`; `api` object with methods:
  - `accounts()`, `createAccount(body)`, `categories()`, `cardholders()`, `merchants()`
  - `transactions(params)`, `createTransaction(body)`, `updateTransaction(id, patch)`, `deleteTransaction(id)`
  - `createRule(body)`, `reapplyRules()`
  - `importFile(accountId, file)`
  - `spendingByCategory(filters)`, `trends(filters)`, `topMerchants(filters)`, `recurring(filters)`
- `FilterBar` props: `{ filters: Filters; onChange: (f: Filters) => void }`; renders date range, cardholder select, account select.
- `App` renders a nav with links to `/` (Dashboard), `/transactions`, `/recurring`, `/import`, `/accounts` inside a `BrowserRouter`. Pages Dashboard, Transactions, Recurring are created in Tasks 14-15; until then `App.tsx` imports them from files created in those tasks, so create temporary one-line stubs (`export default function X() { return <p>Coming soon</p> }`) in Step 4 and replace them later.

- [ ] **Step 1: Write `api.ts`**

`frontend/src/api.ts`:
```ts
import { toQueryString } from './lib/query'

export type AccountType = 'credit_card' | 'checking' | 'savings' | 'other'
export type AccountSource = 'apple_card_csv' | 'manual'
export type Account = {
  id: number
  name: string
  type: AccountType
  source: AccountSource
  starting_balance: number
  starting_balance_date: string | null
}
export type Category = { id: number; name: string; parent_id: number | null }
export type Direction = 'expense' | 'income' | 'refund'
export type Transaction = {
  id: number
  account_id: number
  account_name: string
  transaction_date: string
  posted_date: string | null
  amount: number
  type: string
  merchant: string
  description: string
  cardholder: string | null
  category_id: number
  category: string
  category_source: 'source_default' | 'rule' | 'manual'
  origin: 'import' | 'manual'
}
export type TransactionPage = { items: Transaction[]; total: number }
export type Filters = { date_from?: string; date_to?: string; cardholder?: string; account_id?: string }
export type ManualTransactionInput = {
  account_id: number
  date: string
  amount: number
  direction: Direction
  merchant: string
  description?: string | null
  cardholder?: string | null
  category_id: number
}
export type ImportSummary = {
  batch_id: number
  rows_total: number
  rows_added: number
  rows_skipped: number
  flagged: number
  errors: { line: number; message: string }[]
}
export type CategoryTotal = { category_id: number; category: string; total: number; count: number }
export type MonthTotal = { month: string; total: number }
export type MerchantTotal = { merchant: string; total: number; count: number }
export type RecurringCharge = {
  merchant: string
  cadence: 'weekly' | 'biweekly' | 'monthly' | 'yearly'
  typical_amount: number
  count: number
  last_date: string
  next_expected: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  accounts: () => request<Account[]>('/accounts'),
  createAccount: (body: { name: string; type: AccountType; source: AccountSource }) =>
    request<Account>('/accounts', send('POST', body)),
  categories: () => request<Category[]>('/categories'),
  cardholders: () => request<string[]>('/cardholders'),
  merchants: () => request<string[]>('/merchants'),

  transactions: (params: Record<string, string | number | undefined>) =>
    request<TransactionPage>(`/transactions${toQueryString(params)}`),
  createTransaction: (body: ManualTransactionInput) => request<Transaction>('/transactions', send('POST', body)),
  updateTransaction: (id: number, patch: Partial<Omit<ManualTransactionInput, 'account_id'>>) =>
    request<Transaction>(`/transactions/${id}`, send('PATCH', patch)),
  deleteTransaction: (id: number) => request<void>(`/transactions/${id}`, send('DELETE')),

  createRule: (body: {
    match_field: 'merchant' | 'description'
    match_type: 'contains' | 'equals'
    pattern: string
    category_id: number
  }) => request<unknown>('/rules', send('POST', body)),
  reapplyRules: () => request<{ updated: number }>('/rules/reapply', send('POST')),

  importFile: (accountId: number, file: File) => {
    const form = new FormData()
    form.set('account_id', String(accountId))
    form.set('file', file)
    return request<ImportSummary>('/imports', { method: 'POST', body: form })
  },

  spendingByCategory: (f: Filters) => request<CategoryTotal[]>(`/analytics/spending-by-category${toQueryString(f)}`),
  trends: (f: Filters) => request<MonthTotal[]>(`/analytics/trends${toQueryString(f)}`),
  topMerchants: (f: Filters) => request<MerchantTotal[]>(`/analytics/top-merchants${toQueryString(f)}`),
  recurring: (f: Filters) => request<RecurringCharge[]>(`/analytics/recurring${toQueryString(f)}`),
}
```

- [ ] **Step 2: Write `FilterBar.tsx`**

`frontend/src/components/FilterBar.tsx`:
```tsx
import { api, type Filters } from '../api'
import { useFetch } from '../lib/useFetch'

type Props = { filters: Filters; onChange: (f: Filters) => void }

export default function FilterBar({ filters, onChange }: Props) {
  const cardholders = useFetch(api.cardholders, [])
  const accounts = useFetch(api.accounts, [])
  const set = (key: keyof Filters, value: string) => onChange({ ...filters, [key]: value || undefined })

  return (
    <div className="filter-bar">
      <label>
        From
        <input type="date" value={filters.date_from ?? ''} onChange={(e) => set('date_from', e.target.value)} />
      </label>
      <label>
        To
        <input type="date" value={filters.date_to ?? ''} onChange={(e) => set('date_to', e.target.value)} />
      </label>
      <label>
        Cardholder
        <select value={filters.cardholder ?? ''} onChange={(e) => set('cardholder', e.target.value)}>
          <option value="">All</option>
          {cardholders.data?.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label>
        Account
        <select value={filters.account_id ?? ''} onChange={(e) => set('account_id', e.target.value)}>
          <option value="">All</option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => onChange({})}>
        Clear
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Write Accounts and Import pages**

`frontend/src/pages/Accounts.tsx`:
```tsx
import { useState, type FormEvent } from 'react'
import { api, type AccountSource, type AccountType } from '../api'
import { useFetch } from '../lib/useFetch'

export default function Accounts() {
  const accounts = useFetch(api.accounts, [])
  const [name, setName] = useState('')
  const [type, setType] = useState<AccountType>('checking')
  const [source, setSource] = useState<AccountSource>('manual')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Name is required')
    try {
      await api.createAccount({ name: name.trim(), type, source })
      setName('')
      accounts.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section>
      <h1>Accounts</h1>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {accounts.data?.map((a) => (
            <tr key={a.id}>
              <td>{a.name}</td>
              <td>{a.type}</td>
              <td>{a.source === 'apple_card_csv' ? 'Apple Card CSV import' : 'Manual entry'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {accounts.data?.length === 0 && <p className="muted">No accounts yet. Create your Apple Card account first.</p>}

      <h2>Add account</h2>
      <form onSubmit={submit} className="form-row">
        <input placeholder="Account name" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          <option value="credit_card">Credit card</option>
          <option value="checking">Checking</option>
          <option value="savings">Savings</option>
          <option value="other">Other</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value as AccountSource)}>
          <option value="apple_card_csv">Apple Card CSV import</option>
          <option value="manual">Manual entry</option>
        </select>
        <button type="submit">Add</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
```

`frontend/src/pages/Import.tsx`:
```tsx
import { useState, type DragEvent } from 'react'
import { api, type ImportSummary } from '../api'
import { useFetch } from '../lib/useFetch'

export default function Import() {
  const accounts = useFetch(api.accounts, [])
  const importable = accounts.data?.filter((a) => a.source === 'apple_card_csv') ?? []
  const [accountId, setAccountId] = useState<number | null>(null)
  const [summary, setSummary] = useState<ImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const selected = accountId ?? importable[0]?.id ?? null

  async function upload(file: File) {
    if (selected === null) return setError('Create an Apple Card account first')
    setBusy(true)
    setError(null)
    setSummary(null)
    try {
      setSummary(await api.importFile(selected, file))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) void upload(file)
  }

  return (
    <section>
      <h1>Import</h1>
      {importable.length === 0 ? (
        <p className="muted">
          No Apple Card account yet. Add one on the Accounts page with source &ldquo;Apple Card CSV import&rdquo;.
        </p>
      ) : (
        <>
          <label>
            Account{' '}
            <select value={selected ?? ''} onChange={(e) => setAccountId(Number(e.target.value))}>
              {importable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <div className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
            <p>{busy ? 'Importing…' : 'Drop an Apple Card CSV here, or choose a file'}</p>
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void upload(file)
                e.target.value = ''
              }}
            />
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
      {summary && (
        <div className="summary">
          <p>
            <strong>{summary.rows_added}</strong> added, <strong>{summary.rows_skipped}</strong> skipped as
            duplicates{summary.flagged > 0 && <>, {summary.flagged} with an unrecognized type</>}.
          </p>
          {summary.errors.length > 0 && (
            <>
              <p className="error">{summary.errors.length} row(s) could not be read and were skipped:</p>
              <ul>
                {summary.errors.map((e) => (
                  <li key={e.line}>
                    Line {e.line}: {e.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 4: App shell, styles, stubs**

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import Accounts from './pages/Accounts'
import Dashboard from './pages/Dashboard'
import Import from './pages/Import'
import Recurring from './pages/Recurring'
import Transactions from './pages/Transactions'

const links = [
  ['/', 'Dashboard'],
  ['/transactions', 'Transactions'],
  ['/recurring', 'Recurring'],
  ['/import', 'Import'],
  ['/accounts', 'Accounts'],
] as const

export default function App() {
  return (
    <BrowserRouter>
      <header className="nav">
        <span className="brand">Finio</span>
        {links.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === '/'}>
            {label}
          </NavLink>
        ))}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/import" element={<Import />} />
          <Route path="/accounts" element={<Accounts />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
```

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create temporary stubs (replaced in Tasks 14-15) — each file `frontend/src/pages/{Dashboard,Transactions,Recurring}.tsx` containing:
```tsx
export default function Stub() {
  return <p>Coming soon</p>
}
```
Delete `frontend/src/index.css` if the template created it. Set `<title>Finio</title>` in `frontend/index.html`.

`frontend/src/styles.css`:
```css
:root { font-family: system-ui, sans-serif; color: #1c1e21; background: #f6f7f9; }
body { margin: 0; }
main { max-width: 1100px; margin: 0 auto; padding: 1rem 1.5rem 3rem; }
.nav { display: flex; gap: 1.25rem; align-items: center; padding: 0.75rem 1.5rem; background: #fff; border-bottom: 1px solid #e3e5e8; }
.nav a { color: #555; text-decoration: none; padding: 0.25rem 0; }
.nav a.active { color: #0a5; border-bottom: 2px solid #0a5; }
.brand { font-weight: 700; margin-right: 1rem; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid #eceef1; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.neg { color: #0a7a3a; }
.muted { color: #777; }
.error { color: #b3261e; }
.filter-bar, .form-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: end; margin: 0.75rem 0 1rem; }
.filter-bar label, .form-grid label { display: flex; flex-direction: column; font-size: 0.8rem; color: #555; gap: 0.2rem; }
input, select, button { font: inherit; padding: 0.35rem 0.5rem; }
.dropzone { border: 2px dashed #b9bec6; border-radius: 8px; padding: 2rem; text-align: center; margin: 1rem 0; background: #fff; }
.summary { background: #fff; border: 1px solid #e3e5e8; border-radius: 8px; padding: 0.75rem 1rem; }
.panel { background: #fff; border: 1px solid #e3e5e8; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.75rem; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 800px) { .grid-2 { grid-template-columns: 1fr; } }
.pager { display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem; }
```

- [ ] **Step 5: Verify build and tests**

Run: `cd frontend && npx tsc -b && npm test && npm run build`
Expected: type-check clean, 8 tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: API client, app shell, Accounts and Import screens" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 14: Transactions screen and manual entry form

**Files:**
- Create: `frontend/src/components/AddTransactionForm.tsx`, `frontend/src/pages/Transactions.tsx` (replaces the stub)
- Test: `frontend/src/lib/formValidation.test.ts`, `frontend/src/lib/formValidation.ts`

**Interfaces:**
- Consumes: `api` and types from Task 13; `formatCents`, `parseAmountToCents`; `useFetch`; `FilterBar`.
- Produces:
  - `validateManualForm(v: { accountId: string; date: string; amount: string; merchant: string; categoryId: string }): { ok: true; amountCents: number } | { ok: false; error: string }` in `formValidation.ts`.
  - `AddTransactionForm` props: `{ initial?: Transaction; onDone: () => void; onCancel: () => void }`. With `initial` it PATCHes; otherwise POSTs. Remembers the last used account and date in `localStorage` (wrapped in try/catch), and offers merchant autocomplete via `<datalist>` from `api.merchants()`.

- [ ] **Step 1: Write the failing validation tests**

`frontend/src/lib/formValidation.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { validateManualForm } from './formValidation'

const good = { accountId: '1', date: '2026-09-10', amount: '12.50', merchant: 'Cafe', categoryId: '3' }

describe('validateManualForm', () => {
  it('accepts a complete form and returns cents', () => {
    expect(validateManualForm(good)).toEqual({ ok: true, amountCents: 1250 })
  })
  it('requires each field', () => {
    expect(validateManualForm({ ...good, accountId: '' })).toEqual({ ok: false, error: 'Pick an account' })
    expect(validateManualForm({ ...good, date: '' })).toEqual({ ok: false, error: 'Date is required' })
    expect(validateManualForm({ ...good, amount: 'x' })).toEqual({
      ok: false,
      error: 'Enter an amount greater than 0, like 12.50',
    })
    expect(validateManualForm({ ...good, merchant: '   ' })).toEqual({ ok: false, error: 'Merchant is required' })
    expect(validateManualForm({ ...good, categoryId: '' })).toEqual({ ok: false, error: 'Pick a category' })
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test`
Expected: FAIL (cannot resolve `./formValidation`).

- [ ] **Step 3: Implement validation**

`frontend/src/lib/formValidation.ts`:
```ts
import { parseAmountToCents } from './money'

type Values = { accountId: string; date: string; amount: string; merchant: string; categoryId: string }
type Result = { ok: true; amountCents: number } | { ok: false; error: string }

export function validateManualForm(v: Values): Result {
  if (!v.accountId) return { ok: false, error: 'Pick an account' }
  if (!v.date) return { ok: false, error: 'Date is required' }
  const amountCents = parseAmountToCents(v.amount)
  if (amountCents === null) return { ok: false, error: 'Enter an amount greater than 0, like 12.50' }
  if (!v.merchant.trim()) return { ok: false, error: 'Merchant is required' }
  if (!v.categoryId) return { ok: false, error: 'Pick a category' }
  return { ok: true, amountCents }
}
```

Run: `cd frontend && npm test` — expected: all PASS.

- [ ] **Step 4: Implement the form**

`frontend/src/components/AddTransactionForm.tsx`:
```tsx
import { useState, type FormEvent } from 'react'
import { api, type Direction, type Transaction } from '../api'
import { validateManualForm } from '../lib/formValidation'
import { useFetch } from '../lib/useFetch'

type Props = { initial?: Transaction; onDone: () => void; onCancel: () => void }

const LAST_ACCOUNT = 'finio.lastAccount'
const LAST_DATE = 'finio.lastDate'

function remembered(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}
function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* storage unavailable; the form still works */
  }
}

function directionOf(t: Transaction): Direction {
  return t.type === 'income' ? 'income' : t.type === 'refund' ? 'refund' : 'expense'
}

export default function AddTransactionForm({ initial, onDone, onCancel }: Props) {
  const accounts = useFetch(api.accounts, [])
  const categories = useFetch(api.categories, [])
  const merchants = useFetch(api.merchants, [])

  const [accountId, setAccountId] = useState(initial ? String(initial.account_id) : remembered(LAST_ACCOUNT))
  const [date, setDate] = useState(initial?.transaction_date ?? (remembered(LAST_DATE) || new Date().toISOString().slice(0, 10)))
  const [amount, setAmount] = useState(initial ? (Math.abs(initial.amount) / 100).toFixed(2) : '')
  const [direction, setDirection] = useState<Direction>(initial ? directionOf(initial) : 'expense')
  const [merchant, setMerchant] = useState(initial?.merchant ?? '')
  const [description, setDescription] = useState(initial && initial.description !== initial.merchant ? initial.description : '')
  const [cardholder, setCardholder] = useState(initial?.cardholder ?? '')
  const [categoryId, setCategoryId] = useState(initial ? String(initial.category_id) : '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const check = validateManualForm({ accountId, date, amount, merchant, categoryId })
    if (!check.ok) return setError(check.error)
    setBusy(true)
    try {
      const shared = {
        date,
        amount: check.amountCents,
        direction,
        merchant: merchant.trim(),
        description: description.trim() || null,
        cardholder: cardholder.trim() || null,
        category_id: Number(categoryId),
      }
      if (initial) await api.updateTransaction(initial.id, shared)
      else await api.createTransaction({ account_id: Number(accountId), ...shared })
      remember(LAST_ACCOUNT, accountId)
      remember(LAST_DATE, date)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>{initial ? 'Edit transaction' : 'Add transaction'}</h2>
      <div className="form-grid">
        <label>
          Account
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)} disabled={!!initial}>
            <option value="">Select…</option>
            {accounts.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Amount
          <input inputMode="decimal" placeholder="12.50" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label>
          Type
          <select value={direction} onChange={(e) => setDirection(e.target.value as Direction)}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="refund">Refund</option>
          </select>
        </label>
        <label>
          Merchant
          <input list="merchant-options" value={merchant} onChange={(e) => setMerchant(e.target.value)} />
          <datalist id="merchant-options">
            {merchants.data?.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </label>
        <label>
          Category
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Select…</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Description (optional)
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          Cardholder (optional)
          <input value={cardholder} onChange={(e) => setCardholder(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <button type="submit" disabled={busy}>
          {initial ? 'Save' : 'Add'}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
```

- [ ] **Step 5: Implement the Transactions page**

`frontend/src/pages/Transactions.tsx` (replaces the stub):
```tsx
import { useEffect, useState } from 'react'
import { api, type Filters, type Transaction } from '../api'
import AddTransactionForm from '../components/AddTransactionForm'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

const PAGE_SIZE = 50

export default function Transactions() {
  const [filters, setFilters] = useState<Filters>({})
  const [q, setQ] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [sort, setSort] = useState('date')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(0)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const categories = useFetch(api.categories, [])
  const txns = useFetch(
    () => api.transactions({ ...filters, q, category_id: categoryId, sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [filters, q, categoryId, sort, order, page],
  )

  useEffect(() => setPage(0), [filters, q, categoryId, sort, order])

  async function recategorize(t: Transaction, newCategoryId: number) {
    await api.updateTransaction(t.id, { category_id: newCategoryId })
    txns.reload()
  }

  async function makeRule(t: Transaction) {
    if (!window.confirm(`Always categorize merchants containing "${t.merchant}" as ${t.category}?`)) return
    await api.createRule({ match_field: 'merchant', match_type: 'contains', pattern: t.merchant, category_id: t.category_id })
    const { updated } = await api.reapplyRules()
    setNotice(`Rule created; ${updated} transaction(s) recategorized.`)
    txns.reload()
  }

  async function remove(t: Transaction) {
    if (!window.confirm(`Delete ${t.merchant} on ${t.transaction_date}?`)) return
    await api.deleteTransaction(t.id)
    txns.reload()
  }

  const total = txns.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)

  return (
    <section>
      <h1>Transactions</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      <div className="form-row">
        <input placeholder="Search merchant or description" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={`${sort}:${order}`} onChange={(e) => {
          const [s, o] = e.target.value.split(':')
          setSort(s)
          setOrder(o as 'asc' | 'desc')
        }}>
          <option value="date:desc">Newest first</option>
          <option value="date:asc">Oldest first</option>
          <option value="amount:desc">Largest first</option>
          <option value="amount:asc">Smallest first</option>
          <option value="merchant:asc">Merchant A–Z</option>
        </select>
        <button type="button" onClick={() => { setAdding(true); setEditing(null) }}>
          Add transaction
        </button>
      </div>

      {(adding || editing) && (
        <AddTransactionForm
          key={editing?.id ?? 'new'}
          initial={editing ?? undefined}
          onCancel={() => { setAdding(false); setEditing(null) }}
          onDone={() => { setAdding(false); setEditing(null); txns.reload() }}
        />
      )}

      {notice && <p className="muted">{notice}</p>}
      {txns.error && <p className="error">{txns.error}</p>}

      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Merchant</th>
            <th>Category</th>
            <th>Account</th>
            <th>Cardholder</th>
            <th className="num">Amount</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {txns.data?.items.map((t) => (
            <tr key={t.id}>
              <td>{t.transaction_date}</td>
              <td title={t.description}>{t.merchant}</td>
              <td>
                <select value={t.category_id} onChange={(e) => void recategorize(t, Number(e.target.value))}>
                  {categories.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>{t.account_name}</td>
              <td>{t.cardholder ?? ''}</td>
              <td className={`num ${t.amount < 0 ? 'neg' : ''}`}>{formatCents(t.amount)}</td>
              <td>
                <button type="button" onClick={() => void makeRule(t)}>Make rule</button>{' '}
                {t.origin === 'manual' && (
                  <>
                    <button type="button" onClick={() => { setEditing(t); setAdding(false) }}>Edit</button>{' '}
                    <button type="button" onClick={() => void remove(t)}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {txns.data?.items.length === 0 && !txns.loading && <p className="muted">No transactions match.</p>}

      <div className="pager">
        <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
        <span>
          Page {page + 1} of {lastPage + 1} · {total} transactions
        </span>
        <button type="button" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </section>
  )
}
```

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc -b && npm test && npm run build`
Expected: clean type-check, all tests pass, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat: Transactions screen with manual entry, edit, delete, make-rule" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 15: Dashboard and Recurring screens

**Files:**
- Modify (replace stubs): `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Recurring.tsx`

**Interfaces:**
- Consumes: `api.spendingByCategory`, `api.trends`, `api.topMerchants`, `api.recurring`, `FilterBar`, `formatCents`, `useFetch`.

- [ ] **Step 1: Implement Dashboard**

`frontend/src/pages/Dashboard.tsx`:
```tsx
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Filters } from '../api'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>({})
  const byCategory = useFetch(() => api.spendingByCategory(filters), [filters])
  const trends = useFetch(() => api.trends(filters), [filters])
  const merchants = useFetch(() => api.topMerchants(filters), [filters])

  const grandTotal = byCategory.data?.reduce((sum, c) => sum + c.total, 0) ?? 0
  const empty = byCategory.data?.length === 0

  return (
    <section>
      <h1>Dashboard</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      {(byCategory.error || trends.error || merchants.error) && (
        <p className="error">{byCategory.error ?? trends.error ?? merchants.error}</p>
      )}
      {empty ? (
        <p className="muted">No spending in this range. Import a statement or add a transaction to get started.</p>
      ) : (
        <>
          <p>
            Total spending: <strong>{formatCents(grandTotal)}</strong>
          </p>
          <div className="grid-2">
            <div className="panel">
              <h2>By category</h2>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={byCategory.data ?? []} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(v) => formatCents(Number(v))} />
                  <YAxis type="category" dataKey="category" width={110} />
                  <Tooltip formatter={(v) => formatCents(Number(v))} />
                  <Bar dataKey="total" fill="#2f7d5b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="panel">
              <h2>Monthly trend</h2>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={trends.data ?? []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(v) => formatCents(Number(v))} width={90} />
                  <Tooltip formatter={(v) => formatCents(Number(v))} />
                  <Bar dataKey="total" fill="#3b6ea5" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="panel">
            <h2>Top merchants</h2>
            <table>
              <thead>
                <tr>
                  <th>Merchant</th>
                  <th className="num">Transactions</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {merchants.data?.map((m) => (
                  <tr key={m.merchant}>
                    <td>{m.merchant}</td>
                    <td className="num">{m.count}</td>
                    <td className="num">{formatCents(m.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Implement Recurring**

`frontend/src/pages/Recurring.tsx`:
```tsx
import { useState } from 'react'
import { api, type Filters } from '../api'
import FilterBar from '../components/FilterBar'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

export default function Recurring() {
  const [filters, setFilters] = useState<Filters>({})
  const recurring = useFetch(() => api.recurring(filters), [filters])

  return (
    <section>
      <h1>Recurring charges</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      {recurring.error && <p className="error">{recurring.error}</p>}
      {recurring.data?.length === 0 ? (
        <p className="muted">
          Nothing detected yet. A charge counts as recurring after 3 similar payments at a regular interval.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Merchant</th>
              <th>Cadence</th>
              <th className="num">Typical amount</th>
              <th className="num">Charges</th>
              <th>Last charged</th>
              <th>Next expected</th>
            </tr>
          </thead>
          <tbody>
            {recurring.data?.map((r) => (
              <tr key={r.merchant}>
                <td>{r.merchant}</td>
                <td>{r.cadence}</td>
                <td className="num">{formatCents(r.typical_amount)}</td>
                <td className="num">{r.count}</td>
                <td>{r.last_date}</td>
                <td>{r.next_expected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc -b && npm test && npm run build`
Expected: clean type-check, tests pass, build succeeds. If Recharts' `Tooltip formatter` typing rejects the inline lambda in the installed version, keep the `Number(v)` conversion and adjust only the type annotation.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat: Dashboard and Recurring screens" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 16: README and end-to-end smoke test

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

`README.md`:
````markdown
# Finio

A local, private Mint-style analyzer for Apple Card transactions. Import monthly CSV exports, add transactions from other accounts by hand, and see spending by category, trends, top merchants, and recurring charges. All data stays in a SQLite file on this machine.

## Setup

```bash
# backend (Python 3.13)
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# frontend (Node 22)
cd ../frontend
npm install
```

## Run

```bash
# terminal 1
cd backend && .venv/bin/uvicorn finio.main:app --port 8000

# terminal 2
cd frontend && npm run dev     # open http://localhost:5173
```

The database is created at `backend/data/finio.sqlite3` (override with `FINIO_DB`).

## Use

1. **Accounts**: create an account with source "Apple Card CSV import".
2. **Import**: export a statement CSV from Wallet (Apple Card, Statements) and drop it in. Overlapping exports are safe: rows already stored are skipped.
3. **Transactions**: recategorize inline, use "Make rule" to categorize a merchant automatically from now on, and use "Add transaction" to enter transactions from other sites by hand (pick a category for each).

## Test

```bash
cd backend && .venv/bin/pytest
cd frontend && npm test
```

Never commit real statements: `*.csv` is git-ignored except `backend/tests/fixtures/`, which holds fabricated rows only.
````

- [ ] **Step 2: Run the full automated suites**

Run: `cd backend && .venv/bin/pytest -q && cd ../frontend && npx tsc -b && npm test && npm run build`
Expected: everything passes.

- [ ] **Step 3: Smoke-test the running app**

Start the backend (`cd backend && .venv/bin/uvicorn finio.main:app --port 8000`) and frontend (`cd frontend && npm run dev`) in the background. Use `backend/tests/fixtures/apple_sample.csv` (fabricated data), not the real download. In the browser at `http://localhost:5173`, or with `curl` against `:8000/api`:
1. Create an Apple Card CSV account, import the fixture: expect "6 added, 0 skipped".
2. Import the same file again: expect an error that it was already imported.
3. Dashboard shows Grocery, Restaurants, and Entertainment totals; payment is not counted as spending.
4. Create a manual "Chase" checking account, add an expense with a picked category; it appears in Transactions and on the Dashboard, and Edit/Delete work on it but not on imported rows.
5. Recategorize an imported row, then use "Make rule" and confirm the message reports how many rows changed.

Report any failing step with its output rather than claiming success. Stop both servers when done.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, run, and usage" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|---|---|
| Local web app, FastAPI + React/TS + SQLite | 1, 6, 12 |
| Data model (accounts, batches, transactions, categories, rules, aliases) | 1 |
| Apple CSV importer, sign normalization, unknown type flagged, bad rows reported | 2, 5 |
| Merchant alias cleaning | 3, 5, 8, 9 |
| Dedup: fingerprint + occurrence, file hash, overlapping exports | 3, 5 |
| Raw row stored on imports | 5 |
| Categories seeded from Apple; user rules with priority; rules re-applicable; manual never overwritten | 1, 4, 6, 8, 9 |
| Manual entry: accounts, form fields, required category, edit/delete, imported read-only except category | 6, 8, 14 |
| Manual entry UX: remembered account/date, merchant autocomplete, inline validation | 7, 14 |
| Transactions API filters/sort/paging, cardholder filter | 7, 13, 14 |
| Analytics: by category, trends, top merchants, spending excludes payments/refunds | 10, 15 |
| Recurring detection | 11, 15 |
| UI screens: Dashboard, Transactions, Recurring, Import, Accounts | 13, 14, 15 |
| Testing with fabricated fixtures; no real CSVs committed | 1, 2, 16 |

**Notes for the executor:**
- Balances are stored on accounts (`starting_balance`, `starting_balance_date`) but no UI or endpoint edits them in v1; this matches the spec, which defers the net-worth view.
- The category and alias management UIs are not in v1 screens; categories and aliases are managed through the API, and "Make rule" covers the common flow. Adding them later is a UI-only change.
- Type names used across tasks: `RawTransaction`, `RowError`, `ParseResult`, `ImportSummary`, `where_clause`, `get_transaction`, `create_manual`, `update_transaction`, `delete_transaction`, `find_recurring`, `detect`; frontend `Transaction`, `Filters`, `ManualTransactionInput`, `validateManualForm`.
