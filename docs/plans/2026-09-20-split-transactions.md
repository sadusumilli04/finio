# Split Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user record how much of a purchase was actually theirs ("my share") so group charges they got paid back for don't count as their spending.

**Architecture:** A nullable `my_share` (cents) plus `share_source` on `transactions`. "What the user spent" is `COALESCE(my_share, amount)`, defined once as a SQL constant and read by every query; the API also returns it as `effective_amount`. A migration adds the columns to existing databases (schema version 1 -> 2). The UI adds a Split panel opened from the row menu and shows the share (with the full charge beneath it) in the table.

**Tech Stack:** Python 3.13, FastAPI, stdlib `sqlite3`, pytest; React + TypeScript (Vite 6), Vitest.

**Spec:** `docs/specs/2026-09-20-split-transactions-design.md`

## Global Constraints

- Amounts are integer cents. `amount` (the charge) is never modified by a split, so the app keeps matching the statement.
- `my_share`: nullable integer cents, `>= 0`; `share_source`: `NULL`, `'manual'`, or `'venmo'` (reserved). They are `NULL` together or set together. `NULL` means unsplit, and every transaction starts unsplit (imports and manual creation never set a split; re-import keeps existing splits).
- The effective amount rule `COALESCE(t.my_share, t.amount)` lives in ONE place, `backend/finio/services/amounts.py` (`EFFECTIVE_AMOUNT`); no query re-types the expression. Queries alias the transactions table as `t`.
- Only `type = 'purchase'` can be split; the share must satisfy `0 <= my_share <= amount` (0 allowed); `null` clears. Violations raise `ValidationFailed` (HTTP 400), not 422.
- Imported transactions stay read-only except `category_id` and `my_share`. `POST /api/transactions` does not take `my_share`.
- Analytics (category totals, trends, top merchants) and recurring detection use the effective amount and exclude purchases whose effective amount is 0.
- Transaction list `sort=amount` and `min_amount`/`max_amount` use the effective amount.
- Domain errors come from `finio/errors.py` (no `HTTPException` in services). Routers stay thin.
- Never commit real financial data. Test fixtures use fabricated rows only.
- Frontend: Node is 22.11, so Vite stays pinned to ^6 (do not upgrade vite, @vitejs/plugin-react or vitest). No new dependencies.
- Docs live in `docs/` (the only markdown at the repo root are `README.md` and `CLAUDE.md`).
- Every commit message ends with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (pass as a second `-m`; do not substitute your own model name).
- Backend commands run from `backend/` with `.venv/bin/...`; frontend commands from `frontend/`. Add files to git by path.

---

## File Structure

```
backend/finio/
  db.py                        # MODIFY: new columns in SCHEMA, _migrate(), version 2
  services/amounts.py          # CREATE: EFFECTIVE_AMOUNT constant
  services/filters.py          # MODIFY: min/max amount use EFFECTIVE_AMOUNT
  services/transactions.py     # MODIFY: TXN_SELECT fields, sort, set_share, update_transaction rules
  services/analytics.py        # MODIFY: SUM/exclusion use EFFECTIVE_AMOUNT
  services/recurring.py        # MODIFY: find_recurring uses EFFECTIVE_AMOUNT
  api/transactions.py          # MODIFY: TransactionPatch.my_share
backend/tests/
  helpers.py                   # MODIFY: insert_txn(my_share=, share_source=)
  test_db.py                   # MODIFY: version test + migration tests
  test_split_reads.py          # CREATE: list fields, sort, filters
  test_split_analytics.py      # CREATE: analytics + recurring with splits
  test_split_api.py            # CREATE: PATCH rules, manual edit rules, re-import, venmo hook
frontend/src/
  api.ts                       # MODIFY: Transaction fields, patch type
  lib/split.ts (+ .test.ts)    # CREATE: parseShareToCents, evenShare, validateSplit
  components/SplitPanel.tsx    # CREATE
  pages/Transactions.tsx       # MODIFY: menu items, panel, amount cell
  lib/pinnedRows.test.ts       # MODIFY: fixture gains the new Transaction fields
  styles.css                   # MODIFY: split styles
docs/                          # MODIFY: SPECIFICATION.md, REQUIREMENTS.md; README.md at root
```

---

### Task 1: Schema columns and migration to version 2

**Files:**
- Modify: `backend/finio/db.py`, `backend/tests/helpers.py`, `backend/tests/test_db.py`

**Interfaces:**
- Produces: `transactions.my_share INTEGER` and `transactions.share_source TEXT` (with the CHECK constraints above) on fresh AND migrated databases; `init_db(conn)` leaves `PRAGMA user_version` at 2 (never lowers a higher value); `insert_txn(conn, account_id, *, ..., my_share=None, share_source=None) -> int` (when `my_share` is given without `share_source`, it stores `'manual'`).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_db.py`, change the existing version test to expect 2 and add the new tests (imports `sqlite3`, `pytest`, `connect`, `init_db` already exist):
```python
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
```

In `backend/tests/helpers.py` extend `insert_txn` (add the two keyword arguments and columns):
```python
    source_category=None,
    my_share=None,
    share_source=None,
):
    if my_share is not None and share_source is None:
        share_source = "manual"
    cat_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO transactions(account_id, posted_date, transaction_date, amount, type, "
        "raw_description, merchant_raw, merchant_clean, cardholder, category_id, category_source, origin, "
        "source_category, my_share, share_source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (account_id, posted, date, amount, type, description or merchant, merchant, merchant,
         cardholder, cat_id, category_source, origin, source_category, my_share, share_source),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -q`
Expected: FAIL (no such column `my_share`, version still 1).

- [ ] **Step 3: Implement**

In `backend/finio/db.py`, in the `transactions` table of `SCHEMA` add the two columns after `raw_row` (note the comma):
```sql
    raw_row TEXT,
    my_share INTEGER CHECK (my_share IS NULL OR my_share >= 0),
    share_source TEXT CHECK (share_source IS NULL OR share_source IN ('manual', 'venmo'))
);
```
Add above `connect`:
```python
SCHEMA_VERSION = 2


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to SCHEMA_VERSION. Checks columns rather than trusting the version stamp."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)")}
    if "my_share" not in columns:
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN my_share INTEGER CHECK (my_share IS NULL OR my_share >= 0)"
        )
    if "share_source" not in columns:
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN share_source TEXT "
            "CHECK (share_source IS NULL OR share_source IN ('manual', 'venmo'))"
        )
    if conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
```
In `init_db` replace the old `if conn.execute("PRAGMA user_version")... == 0: ...= 1` block with a call `_migrate(conn)` (keep the category seeding and the final `conn.commit()`).

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (the earlier tests still pass; the helper change is backward compatible).

- [ ] **Step 5: Commit**

```bash
git add backend/finio/db.py backend/tests/test_db.py backend/tests/helpers.py
git commit -m "feat: split columns on transactions with a version 2 migration" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Effective amount in transaction reads (fields, sort, amount filters)

**Files:**
- Create: `backend/finio/services/amounts.py`, `backend/tests/test_split_reads.py`
- Modify: `backend/finio/services/filters.py`, `backend/finio/services/transactions.py`

**Interfaces:**
- Consumes: the new columns and `insert_txn(my_share=...)` (Task 1).
- Produces: `EFFECTIVE_AMOUNT: str` = `"COALESCE(t.my_share, t.amount)"`; every transaction object returned by `GET /api/transactions` and `get_transaction` has `my_share` (int | None), `share_source` (str | None), `effective_amount` (int); `sort=amount`, `min_amount`, `max_amount` operate on the effective amount.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_split_reads.py`:
```python
from tests.helpers import insert_txn


def seed(conn, make_account):
    acct = make_account()
    split = insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, date="2026-09-10")
    plain = insert_txn(conn, acct, merchant="Target", amount=5000, date="2026-09-09")
    payment = insert_txn(conn, acct, merchant="Payment", amount=-10000, type="payment", date="2026-09-08")
    return split, plain, payment


def test_transactions_carry_share_fields(client, conn, make_account):
    split, plain, _ = seed(conn, make_account)
    items = {t["id"]: t for t in client.get("/api/transactions").json()["items"]}
    s = items[split]
    assert (s["amount"], s["my_share"], s["share_source"], s["effective_amount"]) == (12000, 3000, "manual", 3000)
    p = items[plain]
    assert (p["amount"], p["my_share"], p["share_source"], p["effective_amount"]) == (5000, None, None, 5000)


def test_non_purchases_use_their_amount_as_effective(client, conn, make_account):
    _, _, payment = seed(conn, make_account)
    items = {t["id"]: t for t in client.get("/api/transactions").json()["items"]}
    assert items[payment]["effective_amount"] == -10000


def test_sort_by_amount_uses_the_share(client, conn, make_account):
    split, plain, payment = seed(conn, make_account)
    desc = client.get("/api/transactions", params={"sort": "amount", "order": "desc"}).json()["items"]
    assert [t["id"] for t in desc] == [plain, split, payment]  # 5000, 3000 (not 12000), -10000


def test_amount_filters_use_the_share(client, conn, make_account):
    split, plain, _ = seed(conn, make_account)

    def ids(**params):
        return {t["id"] for t in client.get("/api/transactions", params=params).json()["items"]}

    assert ids(min_amount=4000) == {plain}            # the $120 charge is only $30 to the user
    assert ids(max_amount=3000, min_amount=1) == {split}
    assert ids(min_amount=10000) == set()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_split_reads.py -v`
Expected: FAIL (`KeyError: 'my_share'` and sort/filter assertions).

- [ ] **Step 3: Implement**

`backend/finio/services/amounts.py`:
```python
# What the user actually spent on a transaction: their share when it is split, the whole charge otherwise.
# Defined once here so every query agrees. Queries must alias the transactions table as `t`.
EFFECTIVE_AMOUNT = "COALESCE(t.my_share, t.amount)"
```
In `backend/finio/services/filters.py` add `from finio.services.amounts import EFFECTIVE_AMOUNT` and change the two amount conditions to:
```python
    if min_amount is not None:
        add(f"{EFFECTIVE_AMOUNT} >= ?", min_amount)
    if max_amount is not None:
        add(f"{EFFECTIVE_AMOUNT} <= ?", max_amount)
```
In `backend/finio/services/transactions.py` add `from finio.services.amounts import EFFECTIVE_AMOUNT`, extend `TXN_SELECT` and `SORT_COLUMNS`:
```python
TXN_SELECT = f"""
SELECT t.id, t.account_id, a.name AS account_name, t.transaction_date, t.posted_date, t.amount,
       t.type, t.merchant_clean AS merchant, t.raw_description AS description, t.cardholder,
       t.category_id, c.name AS category, t.category_source, t.origin,
       t.my_share, t.share_source, {EFFECTIVE_AMOUNT} AS effective_amount
FROM transactions t
JOIN accounts a ON a.id = t.account_id
JOIN categories c ON c.id = t.category_id
"""

SORT_COLUMNS = {"date": "t.transaction_date", "amount": EFFECTIVE_AMOUNT, "merchant": "t.merchant_clean"}
```

- [ ] **Step 3b: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (existing tests seed unsplit rows, so their sort/filter results are unchanged).

- [ ] **Step 4: Commit**

```bash
git add backend/finio/services/amounts.py backend/finio/services/filters.py backend/finio/services/transactions.py backend/tests/test_split_reads.py
git commit -m "feat: effective amount in transaction reads, sort and amount filters" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Analytics and recurring detection use the share

**Files:**
- Modify: `backend/finio/services/analytics.py`, `backend/finio/services/recurring.py`
- Create: `backend/tests/test_split_analytics.py`

**Interfaces:**
- Consumes: `EFFECTIVE_AMOUNT` (Task 2).
- Produces: `spending_by_category`, `spending_trends`, `top_merchants` sum the effective amount of purchases and exclude purchases with effective amount 0; `find_recurring` uses effective amounts (same exclusion). Endpoint shapes are unchanged.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_split_analytics.py`:
```python
from tests.helpers import insert_txn


def test_category_totals_use_the_share(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, category="Restaurants")
    insert_txn(conn, acct, merchant="Cafe", amount=1000, category="Restaurants")
    data = client.get("/api/analytics/spending-by-category").json()
    assert [(d["category"], d["total"], d["count"]) for d in data] == [("Restaurants", 4000, 2)]


def test_trends_and_merchants_use_the_share(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, merchant="Home Plate", amount=12000, my_share=3000, date="2026-09-10")
    insert_txn(conn, acct, merchant="Home Plate", amount=8000, date="2026-08-10")
    assert client.get("/api/analytics/trends").json() == [
        {"month": "2026-08", "total": 8000},
        {"month": "2026-09", "total": 3000},
    ]
    assert client.get("/api/analytics/top-merchants").json() == [
        {"merchant": "Home Plate", "total": 11000, "count": 2},
    ]


def test_fully_repaid_purchase_leaves_analytics_but_stays_in_the_list(client, conn, make_account):
    acct = make_account()
    zero = insert_txn(conn, acct, merchant="Birthday Dinner", amount=20000, my_share=0, category="Restaurants")
    insert_txn(conn, acct, merchant="Cafe", amount=1500, category="Grocery")
    cats = client.get("/api/analytics/spending-by-category").json()
    assert [(c["category"], c["total"]) for c in cats] == [("Grocery", 1500)]
    merchants = client.get("/api/analytics/top-merchants").json()
    assert [m["merchant"] for m in merchants] == ["Cafe"]
    assert [t["id"] for t in client.get("/api/transactions", params={"q": "birthday"}).json()["items"]] == [zero]


def test_recurring_uses_the_share(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, merchant="Book Club Dinner", amount=6000, my_share=2000, date=d)
    data = client.get("/api/analytics/recurring").json()
    assert [(r["merchant"], r["typical_amount"], r["cadence"]) for r in data] == [("Book Club Dinner", 2000, "monthly")]


def test_recurring_ignores_fully_repaid_charges(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, merchant="Covered Dinner", amount=6000, my_share=0, date=d)
    assert client.get("/api/analytics/recurring").json() == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_split_analytics.py -v`
Expected: FAIL (totals use the full charge).

- [ ] **Step 3: Implement**

`backend/finio/services/analytics.py`: add `from finio.services.amounts import EFFECTIVE_AMOUNT`, and rewrite the three queries to use it:
```python
def _spending_where(**filters) -> tuple[str, list]:
    where, params = where_clause(**filters)
    return f"t.type = 'purchase' AND {EFFECTIVE_AMOUNT} > 0 AND {where}", params
```
Replace every `SUM(t.amount)` with `SUM({EFFECTIVE_AMOUNT})` (the SELECT strings that contain it must become f-strings; keep the existing `{where}` interpolation and `ORDER BY`/`GROUP BY`/`LIMIT` clauses exactly as they are).

`backend/finio/services/recurring.py::find_recurring`: add the same import and change the query to:
```python
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, t.transaction_date AS d, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE t.type = 'purchase' AND {EFFECTIVE_AMOUNT} > 0 "
        f"AND t.merchant_clean != '' AND {where}",
        params,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (unsplit data behaves as before).

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/analytics.py backend/finio/services/recurring.py backend/tests/test_split_analytics.py
git commit -m "feat: analytics and recurring detection use the user's share" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Setting and clearing a split (service + API)

**Files:**
- Modify: `backend/finio/services/transactions.py`, `backend/finio/api/transactions.py`
- Create: `backend/tests/test_split_api.py`

**Interfaces:**
- Consumes: columns (Task 1), transaction fields (Task 2).
- Produces:
  - `set_share(conn, transaction_id: int, my_share: int | None, source: str = "manual") -> dict` returns the updated transaction object; raises `NotFoundError` (unknown id) and `ValidationFailed` (not a purchase, or share outside `0..charge`); `None` clears both columns. This is also the entry point a future Venmo importer uses with `source="venmo"`.
  - `PATCH /api/transactions/{id}` accepts `my_share` (int cents or `null`); for imported rows the allowed fields become `{category_id, my_share}` (anything else -> 403 as before); an explicit `null` is valid for `my_share` only. Setting a share stores `share_source = 'manual'`.
  - Manual-row edit rules: lowering `amount` below the existing `my_share` without changing the share -> 400 ("The split exceeds the new charge; edit the split first"); changing `direction` away from `expense` clears the split; `amount` + `my_share` in the same PATCH are validated together against the new amount.
  - `TransactionPatch.my_share: int | None` (no `ge`, so negatives reach the service and return 400; `le=10**12`). `POST /api/transactions` is unchanged and ignores any `my_share` in the body.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_split_api.py`:
```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_split_api.py -v`
Expected: FAIL (`ImportError: cannot import name 'set_share'`, and PATCH ignores/rejects `my_share`).

- [ ] **Step 3: Implement the service**

In `backend/finio/services/transactions.py` add these helpers below `_require_category`:
```python
SHARE_FIELDS = {"category_id", "my_share"}


def _share_columns(row, my_share, source: str = "manual", *, new_type=None, new_amount=None) -> dict:
    """Column updates that set or clear the split, validated against the (possibly just-edited) charge."""
    if my_share is None:
        return {"my_share": None, "share_source": None}
    type_ = new_type or row["type"]
    charge = abs(new_amount) if new_amount is not None else row["amount"]
    if type_ != "purchase":
        raise ValidationFailed("Only purchases can be split")
    if my_share < 0 or my_share > charge:
        raise ValidationFailed("Your share must be between $0.00 and the charge")
    return {"my_share": my_share, "share_source": source}


def set_share(conn: sqlite3.Connection, transaction_id: int, my_share: int | None, source: str = "manual") -> dict:
    """Set (or clear, with None) how much of a purchase is the user's. Other sources, such as a Venmo importer, call this too."""
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    sets = _share_columns(row, my_share, source)
    with conn:
        conn.execute(
            "UPDATE transactions SET my_share = ?, share_source = ? WHERE id = ?",
            (sets["my_share"], sets["share_source"], transaction_id),
        )
    return get_transaction(conn, transaction_id)
```
In `update_transaction`:
1. Change the imported-row guard to
```python
    if row["origin"] == "import" and set(fields) - SHARE_FIELDS:
        raise ForbiddenError("Imported transactions can only be recategorized or split")
```
(if an existing test asserts the old message text, update it to the new one; tests assert 403.)
2. Leave the "Reject explicit nulls" loop as is (`my_share` is intentionally not in its list).
3. After the `if row["origin"] == "manual": ...` block and BEFORE `if sets:`, add:
```python
    if "my_share" in fields:
        sets.update(_share_columns(row, fields["my_share"], new_type=sets.get("type"), new_amount=sets.get("amount")))
    elif row["my_share"] is not None and ("amount" in sets or "type" in sets):
        if sets.get("type", row["type"]) != "purchase":
            sets["my_share"] = None
            sets["share_source"] = None
        elif sets.get("amount", row["amount"]) < row["my_share"]:
            raise ValidationFailed("The split exceeds the new charge; edit the split first")
```

- [ ] **Step 4: Implement the API model**

In `backend/finio/api/transactions.py`, add to `TransactionPatch`:
```python
    my_share: int | None = Field(default=None, le=10**12)
```
No other API change (the route already passes `body.model_dump(exclude_unset=True)`, which keeps an explicit `null`).

- [ ] **Step 5: Run to verify they pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (including the earlier manual-transaction tests: imported-row rejection is still 403; explicit-null rejection for merchant/date/amount/direction is unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/finio/services/transactions.py backend/finio/api/transactions.py backend/tests/test_split_api.py
git commit -m "feat: set and clear a split through PATCH /transactions" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend types and split helpers

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/lib/pinnedRows.test.ts`
- Create: `frontend/src/lib/split.ts`, `frontend/src/lib/split.test.ts`

**Interfaces:**
- Produces:
  - `Transaction` gains `my_share: number | null`, `share_source: 'manual' | 'venmo' | null`, `effective_amount: number`.
  - `api.updateTransaction(id, patch)` patch type gains `my_share?: number | null`.
  - `parseShareToCents(input: string): number | null` — like `parseAmountToCents` (accepts `"30"`, `"30.5"`, `"$1,234.56"`) but ALSO accepts zero (`"0"`, `"0.00"` -> 0); returns `null` for blank, non-numeric, negative, or more than 2 decimals.
  - `evenShare(chargeCents: number, people: number): number | null` — `Math.round(chargeCents / people)` for a whole `people >= 2`, else `null`.
  - `validateSplit(text: string, chargeCents: number): { ok: true; cents: number } | { ok: false; error: string }` — errors: blank/invalid -> `"Enter your share, like 30.00"`; above the charge -> `` `Your share can't be more than the charge (${formatCents(chargeCents)})` ``.

- [ ] **Step 1: Write the failing tests**

`frontend/src/lib/split.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { evenShare, parseShareToCents, validateSplit } from './split'

describe('parseShareToCents', () => {
  it('parses plain and formatted amounts', () => {
    expect(parseShareToCents('30')).toBe(3000)
    expect(parseShareToCents('30.5')).toBe(3050)
    expect(parseShareToCents('$1,234.56')).toBe(123456)
    expect(parseShareToCents(' 0.07 ')).toBe(7)
  })
  it('accepts zero, unlike the general amount parser', () => {
    expect(parseShareToCents('0')).toBe(0)
    expect(parseShareToCents('0.00')).toBe(0)
  })
  it('rejects invalid input', () => {
    expect(parseShareToCents('')).toBeNull()
    expect(parseShareToCents('abc')).toBeNull()
    expect(parseShareToCents('-5')).toBeNull()
    expect(parseShareToCents('1.234')).toBeNull()
  })
})

describe('evenShare', () => {
  it('divides the charge and rounds to the nearest cent', () => {
    expect(evenShare(12000, 4)).toBe(3000)
    expect(evenShare(10000, 3)).toBe(3333)
    expect(evenShare(10001, 2)).toBe(5001)
  })
  it('needs a whole number of at least two people', () => {
    expect(evenShare(12000, 1)).toBeNull()
    expect(evenShare(12000, 0)).toBeNull()
    expect(evenShare(12000, 2.5)).toBeNull()
    expect(evenShare(12000, Number.NaN)).toBeNull()
  })
})

describe('validateSplit', () => {
  it('accepts an amount up to and including the charge, and zero', () => {
    expect(validateSplit('30.00', 12000)).toEqual({ ok: true, cents: 3000 })
    expect(validateSplit('120', 12000)).toEqual({ ok: true, cents: 12000 })
    expect(validateSplit('0', 12000)).toEqual({ ok: true, cents: 0 })
  })
  it('rejects blank, invalid, and too-large values with a clear message', () => {
    expect(validateSplit('', 12000)).toEqual({ ok: false, error: 'Enter your share, like 30.00' })
    expect(validateSplit('abc', 12000)).toEqual({ ok: false, error: 'Enter your share, like 30.00' })
    expect(validateSplit('120.01', 12000)).toEqual({
      ok: false,
      error: "Your share can't be more than the charge ($120.00)",
    })
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL (cannot resolve `./split`).

- [ ] **Step 3: Implement**

`frontend/src/lib/split.ts`:
```ts
import { formatCents } from './money'

const ENTER_SHARE = 'Enter your share, like 30.00'

// Like parseAmountToCents, but zero is a valid share (someone else covered the whole charge).
export function parseShareToCents(input: string): number | null {
  const cleaned = input.trim().replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null
  const [dollars, fraction = ''] = cleaned.split('.')
  return parseInt(dollars, 10) * 100 + parseInt(fraction.padEnd(2, '0') || '0', 10)
}

export function evenShare(chargeCents: number, people: number): number | null {
  if (!Number.isInteger(people) || people < 2) return null
  return Math.round(chargeCents / people)
}

export function validateSplit(
  text: string,
  chargeCents: number,
): { ok: true; cents: number } | { ok: false; error: string } {
  const cents = parseShareToCents(text)
  if (cents === null) return { ok: false, error: ENTER_SHARE }
  if (cents > chargeCents) {
    return { ok: false, error: `Your share can't be more than the charge (${formatCents(chargeCents)})` }
  }
  return { ok: true, cents }
}
```
In `frontend/src/api.ts`: add to the `Transaction` type
```ts
  my_share: number | null
  share_source: 'manual' | 'venmo' | null
  effective_amount: number
```
and change the `updateTransaction` patch type to
`Partial<Omit<ManualTransactionInput, 'account_id'>> & { my_share?: number | null }`.
In `frontend/src/lib/pinnedRows.test.ts` add `my_share: null, share_source: null, effective_amount: 1000,` to the `txn()` fixture so it still satisfies the type (its `amount` is 1000).

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && ./node_modules/.bin/tsc -b && npm test`
Expected: type-check clean; all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/lib/split.ts frontend/src/lib/split.test.ts frontend/src/lib/pinnedRows.test.ts
git commit -m "feat: split types and helpers for the frontend" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Split panel and the Transactions table

**Files:**
- Create: `frontend/src/components/SplitPanel.tsx`
- Modify: `frontend/src/pages/Transactions.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `Transaction`, `api.updateTransaction`, `validateSplit`, `evenShare`, `parseShareToCents`, `formatCents`, `RowMenu` (existing).
- Produces: `SplitPanel` props `{ transaction: Transaction; onDone: () => void; onCancel: () => void }`. The Transactions page shows a "Split…" row-menu item on purchases (`t.type === 'purchase'`), "Edit split…" and "Remove split" on split ones, opens the panel above the table, and shows the share bold with "of $X" beneath when split.

- [ ] **Step 1: Create the panel**

`frontend/src/components/SplitPanel.tsx`:
```tsx
import { useState, type FormEvent } from 'react'
import { api, type Transaction } from '../api'
import { formatCents } from '../lib/money'
import { evenShare, parseShareToCents, validateSplit } from '../lib/split'

type Props = { transaction: Transaction; onDone: () => void; onCancel: () => void }

export default function SplitPanel({ transaction: t, onDone, onCancel }: Props) {
  const [people, setPeople] = useState('')
  const [share, setShare] = useState(t.my_share === null ? '' : (t.my_share / 100).toFixed(2))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const typed = parseShareToCents(share)
  const paidForOthers = typed !== null && typed <= t.amount ? t.amount - typed : null

  function fillIn() {
    const cents = evenShare(t.amount, Number(people))
    if (cents === null) return setError('Enter a whole number of people, 2 or more')
    setError(null)
    setShare((cents / 100).toFixed(2))
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const check = validateSplit(share, t.amount)
    if (!check.ok) return setError(check.error)
    await send(check.cents)
  }

  async function send(myShare: number | null) {
    setBusy(true)
    try {
      await api.updateTransaction(t.id, { my_share: myShare })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel split-panel" onSubmit={save}>
      <div className="split-head">
        <h2>Split “{t.merchant}”</h2>
        <span className="muted">Charge: {formatCents(t.amount)}</span>
      </div>
      <div className="split-row">
        <label>
          Split evenly among
          <input inputMode="numeric" size={4} placeholder="4" value={people} onChange={(e) => setPeople(e.target.value)} />
          <span>people</span>
        </label>
        <button type="button" onClick={fillIn}>Fill in</button>
      </div>
      <div className="split-row">
        <label>
          My share ($)
          <input inputMode="decimal" size={10} value={share} onChange={(e) => setShare(e.target.value)} autoFocus />
        </label>
        <span className="muted split-others">
          {paidForOthers === null ? '' : `Paid for others: ${formatCents(paidForOthers)}`}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="form-row">
        <button type="submit" disabled={busy}>Save split</button>
        <button type="button" onClick={onCancel}>Cancel</button>
        {t.my_share !== null && (
          <button type="button" disabled={busy} onClick={() => void send(null)}>Remove split</button>
        )}
      </div>
    </form>
  )
}
```

- [ ] **Step 2: Wire it into the Transactions page**

In `frontend/src/pages/Transactions.tsx`:
1. `import SplitPanel from '../components/SplitPanel'`.
2. Add state next to `editing`: `const [splitting, setSplitting] = useState<Transaction | null>(null)`.
3. Add a handler beside `remove`:
```tsx
  async function removeSplit(t: Transaction) {
    setActionError(null)
    setNotice(null)
    try {
      await api.updateTransaction(t.id, { my_share: null })
      txns.reload()
    } catch (err) {
      setActionError(messageOf(err))
    }
  }
```
4. Opening the Add/Edit form or the Split panel must close the others: in the existing `onClick`s that call `setAdding(true)` / `setEditing(t)` also call `setSplitting(null)`.
5. Render the panel next to the existing Add/Edit form block:
```tsx
      {splitting && (
        <SplitPanel
          key={splitting.id}
          transaction={splitting}
          onCancel={() => setSplitting(null)}
          onDone={() => { setSplitting(null); txns.reload() }}
        />
      )}
```
6. In the `RowMenu` items array, put these first (before "Make rule"), only for purchases:
```tsx
                        ...(t.type === 'purchase'
                          ? t.my_share === null
                            ? [{ label: 'Split…', onSelect: () => { setSplitting(t); setAdding(false); setEditing(null) } }]
                            : [
                                { label: 'Edit split…', onSelect: () => { setSplitting(t); setAdding(false); setEditing(null) } },
                                { label: 'Remove split', onSelect: () => void removeSplit(t) },
                              ]
                          : []),
```
7. Replace the amount cell with:
```tsx
                  <td className={`num cell-amount ${t.effective_amount < 0 ? 'neg' : ''}`}>
                    {formatCents(t.effective_amount)}
                    {t.my_share !== null && <span className="amount-of">of {formatCents(t.amount)}</span>}
                  </td>
```
8. Update the filter-panel hint text to: `Amounts are what you spent on each transaction (your share, if it is split); payments and refunds are negative.`

- [ ] **Step 3: Styles**

Append to `frontend/src/styles.css` (all scoped so other pages are unaffected):
```css
/* ---- Transactions: split panel and split amounts ------------------------------------- */
.txn-page .amount-of { display: block; font-size: 0.8125rem; font-weight: 400; color: var(--muted); }
.split-panel .split-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.split-panel .split-head h2 { margin: 0; }
.split-panel .split-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; margin: 0.75rem 0; }
.split-panel .split-row label { display: flex; align-items: center; gap: 0.5rem; }
.split-panel .split-others { min-width: 12rem; }
```

- [ ] **Step 4: Verify**

Run: `cd frontend && ./node_modules/.bin/tsc -b && npm test && npm run build`
Expected: type-check clean, tests pass, build succeeds. (Visual and click-through verification happens in Task 7.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SplitPanel.tsx frontend/src/pages/Transactions.tsx frontend/src/styles.css
git commit -m "feat: split panel and share display on the Transactions page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Docs and end-to-end verification

**Files:**
- Modify: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `README.md`

- [ ] **Step 1: Update the docs**

- `docs/SPECIFICATION.md`: in the `transactions` data-model bullet add `my_share` (cents, nullable) and `share_source` (`manual`, reserved `venmo`), with a sentence that the effective amount is `COALESCE(my_share, amount)` and the charge is never modified; in the spending/analytics text say spending, trends, top merchants and recurring use the user's share and exclude purchases whose share is 0; in the API section document `PATCH /transactions/{id}` `my_share` (null clears; imported rows may be split) and the new `my_share`/`share_source`/`effective_amount` fields, and that sort/amount filters use the effective amount; in the UI section add the Split panel and the share-over-charge display; mention schema version 2.
- `docs/REQUIREMENTS.md`: add `R32`–`R36`: (R32) a transaction can be split so only the user's share counts as spending; (R33) transactions start unsplit and the user opts in per transaction; (R34) the split is entered as an exact amount, with an even-split-among-N shortcut; (R35) the original charge stays intact and visible; (R36) the design leaves a place for a later Venmo integration to set the share. Under "Out of scope for v1" note Venmo, per-person amounts, and tracking money owed.
- `README.md`: in the "Use" section add one bullet: "Split a group charge: open a purchase's ⋯ menu and choose Split… to enter what you actually spent (or split evenly among N people). Only your share counts on the Dashboard; the full charge stays on the transaction."

- [ ] **Step 2: Run the full automated suites**

Run: `cd backend && .venv/bin/pytest -q` and `cd frontend && ./node_modules/.bin/tsc -b && npm test && npm run build`
Expected: everything passes.

- [ ] **Step 3: Verify the whole flow against a throwaway app**

Use a throwaway database and fabricated data only (never a real file): start the backend on port 8001 with `FINIO_DB=/tmp/finio-split.sqlite3` and a temporary Vite config in `frontend/` (untracked, delete afterwards) on port 5174 proxying `/api` to `http://127.0.0.1:8001`; do not touch the ports 5173/8000 servers.
1. Through the API: create an account, import `backend/tests/fixtures/apple_sample.csv`, add a manual expense; confirm `PATCH my_share` on an imported purchase returns `effective_amount` and that `GET /api/analytics/spending-by-category` reflects the share; confirm a payment can't be split (400), a share above the charge is rejected (400), `0` is accepted and the row leaves the analytics, and `null` restores the full charge.
2. Migration on a copy of an OLD-schema database: build a database with the pre-split `transactions` table (see `OLD_TRANSACTIONS_DDL` in `backend/tests/test_db.py`), start the backend against it, and confirm it starts, keeps the data, and reports `PRAGMA user_version = 2`.
3. In the browser (Playwright tools if available): on the Transactions page open a purchase's ⋯ menu, choose Split…, use "Split evenly among 4" + Fill in, save, and confirm the row shows the share in bold with "of $X" beneath; check the Dashboard totals changed; remove the split and confirm the full charge returns. Check desktop and phone widths and the browser console for errors. If the browser tooling is unavailable, say so.
4. Stop both servers and delete the temporary database and Vite config.
Report every check with its result; do not fix application code in this task — report defects as findings.

- [ ] **Step 4: Commit**

```bash
git add docs/SPECIFICATION.md docs/REQUIREMENTS.md README.md
git commit -m "docs: document split transactions" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|---|---|
| `my_share` / `share_source` columns, CHECK constraints, original amount untouched | 1 |
| Migration to version 2 for existing, stamped-0 and fresh databases; never lowers | 1 |
| Effective amount defined once (`amounts.py`) | 2 |
| `effective_amount`, `my_share`, `share_source` on every transaction object | 2 |
| Sort and min/max amount use the effective amount | 2 |
| Category totals, trends, top merchants use the share; zero-share excluded | 3 |
| Recurring uses the share; zero-share excluded | 3 |
| Only purchases; `0 <= share <= charge`; `null` clears; 400s | 4 |
| Imported rows: category + share only; other fields still 403 | 4 |
| Manual edits: amount below share rejected, direction change clears, joint validation | 4 |
| `POST` does not take `my_share`; new transactions unsplit | 4 |
| Re-import and rules never touch a split | 4 |
| `share_source` = manual now; `set_share(source="venmo")` hook | 4 |
| Even-split rounding, zero-allowing parser, validation | 5 |
| Row menu Split…/Edit split…/Remove split; split panel; share bold with "of $X" | 6 |
| Dashboard reflects the share (no UI change) | 3 |
| Docs (spec, requirements, README) | 7 |
| Browser/API/migration verification | 7 |

**Notes for the executor:** existing tests seed unsplit rows and should keep passing unchanged, except `test_schema_version_stamped_and_not_lowered`, which Task 1 updates to expect version 2. The Dashboard needs no code change: it renders whatever the analytics endpoints return.
