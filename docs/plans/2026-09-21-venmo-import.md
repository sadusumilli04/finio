# Venmo CSV Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import Venmo account statements (CSV) so Venmo transactions behave like Apple Card ones: duplicate-safe imports, categories and rules, Transactions page, splits, Dashboard and Insights.

**Architecture:** One new importer class (`VenmoCsvImporter`) registered in `IMPORTERS`, the pattern the Apple importer follows. `RawTransaction` gains an optional `external_id`, which `fingerprint()` uses when present so Venmo rows dedup by their real transaction ID. Ingestion, rules, analytics and insights are unchanged: Venmo payments you send are `purchase`, money you receive is `payment` (money in), bank transfers are `transfer`.

**Tech Stack:** Python 3.13, FastAPI, stdlib `csv`/`decimal`, sqlite3, pytest; React + TypeScript (one dropdown option and a label).

**Spec:** `docs/specs/2026-09-21-venmo-import-design.md`

## Global Constraints

- Work on branch `venmo` in the main project folder. No git worktrees. Do not push, open PRs or merge.
- Amounts are integer cents (positive = money spent, negative = money in). Never floats for money; parse with `Decimal`.
- Spending in analytics is `type = 'purchase'` only. Do not change analytics, insights, rules or splits code.
- Apple Card dedup must not change: `fingerprint()` keeps its existing recipe when `external_id` is `None`, and every existing test stays green.
- Domain errors go through `finio/errors.py` (`ValidationFailed` etc.), never `HTTPException` in services or importers (importers raise `ValueError`, ingestion maps it to `ValidationFailed`).
- **Never commit real financial data.** Fixtures are fabricated (`backend/tests/fixtures/`). Do not read or copy any real statement (for example from `~/Downloads`).
- Docs live in `docs/` (README.md and CLAUDE.md stay at the root).
- Frontend: Vite ^6 stays pinned; type-check with `./node_modules/.bin/tsc -b`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## File Structure

- Modify `backend/finio/importers/base.py`: `RawTransaction.external_id`.
- Modify `backend/finio/services/dedup.py`: fingerprint uses `external_id`.
- Create `backend/finio/importers/venmo_csv.py`: the importer.
- Modify `backend/finio/services/ingestion.py`: register `"venmo_csv"`.
- Modify `backend/finio/api/accounts.py`, `frontend/src/api.ts`, `frontend/src/pages/Accounts.tsx`: new account source.
- Create `backend/tests/fixtures/venmo_sample.csv`, `backend/tests/test_venmo_importer.py`, `backend/tests/test_venmo_ingestion.py`.
- Modify docs: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, `README.md`, `CLAUDE.md`.

---

### Task 1: The Venmo importer and ID-based dedup

**Files:**
- Modify: `backend/finio/importers/base.py`, `backend/finio/services/dedup.py`
- Create: `backend/finio/importers/venmo_csv.py`, `backend/tests/fixtures/venmo_sample.csv`, `backend/tests/test_venmo_importer.py`
- Modify: `backend/tests/test_merchants_dedup.py` (add fingerprint tests; check the file for the existing fingerprint tests' style first)

**Interfaces:**
- Consumes: `ParseResult`, `RawTransaction`, `RowError` from `importers/base.py`.
- Produces:
  - `RawTransaction.external_id: str | None = None` (new last field, after `flagged`).
  - `fingerprint(account_id, r)`: when `r.external_id` is set, returns `sha256("|".join([str(account_id), "id", r.external_id]))`; otherwise the existing recipe.
  - `VenmoCsvImporter().parse(content: bytes) -> ParseResult`.

Row mapping the importer implements (from the spec): the signed amount `- $X` means you paid, `+ $X` means you received.
| Venmo row | `type` | `amount` cents | `merchant_raw` | `source_category` |
|---|---|---|---|---|
| `Payment`/`Charge`, sign `-` | `purchase` | `+X` | Payment: `To`; Charge: `From` | `Friends & Family` |
| `Payment`/`Charge`, sign `+` | `payment` | `-X` | Payment: `From`; Charge: `To` | `Friends & Family` |
| `Standard Transfer` / `Instant Transfer` | `transfer` | `+X` if sign `-`, else `-X` | `Venmo transfer` | `Other` |
| any other `Type` | `other`, `flagged=True` | `+X` if sign `-`, else `-X` | counterparty as for Payment | `Friends & Family` |

Also: `raw_description` = the Note, or `Venmo payment` / `Venmo charge` / the type text lowercased-as-is (`Standard Transfer`) when the note is blank; `transaction_date` = first 10 characters of `Datetime`; `posted_date = None`; `cardholder = None`; `external_id` = the `ID`; `raw_row` = the row as a dict of header to string. Rows whose `Status` (case-insensitive) is not `Complete` or `Issued` are NOT imported: they produce `RowError(line, "status: <Status>")`. A repeated `ID` inside one file is skipped silently (first wins). Title, `Account Activity`, balance, footer and disclaimer rows (no `ID`) are skipped silently. Header detection: the first row containing both `ID` and `Datetime` cells; if none, `raise ValueError("Not a Venmo CSV; missing columns: ['Datetime', 'ID']")` (list the missing required columns `ID`, `Datetime`, `Type`, `Status`, `Amount (total)`, sorted; if the header row is found but lacks some, list those).

- [ ] **Step 1: Create the fabricated fixture**

`backend/tests/fixtures/venmo_sample.csv` (fabricated; keep the exact column layout: a leading empty column, 22 fields per row):
```
Account Statement - (@test-user) ,,,,,,,,,,,,,,,,,,,,,
Account Activity,,,,,,,,,,,,,,,,,,,,,
,ID,Datetime,Type,Status,Note,From,To,Amount (total),Amount (tip),Amount (tax),Amount (fee),Tax Rate,Tax Exempt,Funding Source,Destination,Beginning Balance,Ending Balance,Statement Period Venmo Fees,Terminal Location,Year to Date Venmo Fees,Disclaimer
,,,,,,,,,,,,,,,,$10.00,,,,,
,1000000000000000001,2026-09-10T09:15:00,Payment,Complete,groceries,Test User,Person One,- $23.40,,0,,0,,"TEST BANK Checking *0000",,,,,Venmo,,
,1000000000000000002,2026-09-10T11:30:00,Charge,Complete,Lunch,Person Two,Test User,- $8.25,,0,,0,,"TEST BANK Checking *0000",,,,,Venmo,,
,1000000000000000003,2026-09-13T08:00:00,Standard Transfer,Issued,,,,- $30.00,,,,,,,"TEST BANK *0000",,,,Venmo,,
,1000000000000000004,2026-09-13T09:45:00,Payment,Complete,Dinner,Person One,Test User,+ $37.10,,0,,0,,,Venmo balance,,,,Venmo,,
,1000000000000000005,2026-09-13T14:20:00,Charge,Complete,coffee run,Test User,Person Three,+ $48.90,,0,,0,,,Venmo balance,,,,Venmo,,
,1000000000000000006,2026-09-14T10:00:00,Payment,Complete,Rent share,Test User,Person Four,"- $1,250.00",,0,,0,,"TEST BANK Checking *0000",,,,,Venmo,,
,1000000000000000007,2026-09-15T10:00:00,Payment,Cancelled,Oops,Test User,Person One,- $5.00,,0,,0,,"TEST BANK Checking *0000",,,,,Venmo,,
,1000000000000000008,2026-09-16T10:00:00,Payment,Complete,,Test User,Person Two,- $7.50,,0,,0,,"TEST BANK Checking *0000",,,,,Venmo,,
,,,,,,,,,,,,,,,,,$0.00,$0.00,,$0.00,"In case of errors or questions about your
        electronic transfers:
        - Telephone us at 000-000-0000
        (this is a fabricated test disclaimer)
        "
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_venmo_importer.py`:
```python
from pathlib import Path

import pytest

from finio.importers.base import RawTransaction
from finio.importers.venmo_csv import VenmoCsvImporter
from finio.services.dedup import fingerprint

FIXTURE = (Path(__file__).parent / "fixtures" / "venmo_sample.csv").read_bytes()
HEADER = (
    b"Account Statement - (@x) ,,,,,\nAccount Activity,,,,,\n"
    b",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
)


def parse(content=FIXTURE):
    return VenmoCsvImporter().parse(content)


def by_id(result):
    return {r.external_id: r for r in result.rows}


def test_reads_only_transaction_rows_and_reports_the_cancelled_one():
    result = parse()
    assert len(result.rows) == 7                                # 8 transaction rows, one cancelled
    assert [e.message for e in result.errors] == ["status: Cancelled"]
    assert result.errors[0].line > 0
    assert "1000000000000000007" not in by_id(result)


def test_payment_you_send_is_a_purchase_to_the_payee():
    r = by_id(parse())["1000000000000000001"]
    assert (r.type, r.amount, r.merchant_raw, r.raw_description) == ("purchase", 2340, "Person One", "groceries")
    assert (r.transaction_date, r.posted_date, r.cardholder, r.source_category) == ("2026-09-10", None, None, "Friends & Family")
    assert r.flagged is False


def test_charge_you_pay_is_a_purchase_to_the_requester():
    r = by_id(parse())["1000000000000000002"]
    assert (r.type, r.amount, r.merchant_raw) == ("purchase", 825, "Person Two")


def test_money_you_receive_is_money_in():
    rows = by_id(parse())
    payment_in, charge_paid = rows["1000000000000000004"], rows["1000000000000000005"]
    assert (payment_in.type, payment_in.amount, payment_in.merchant_raw) == ("payment", -3710, "Person One")
    assert (charge_paid.type, charge_paid.amount, charge_paid.merchant_raw) == ("payment", -4890, "Person Three")


def test_standard_transfer_is_not_spending():
    r = by_id(parse())["1000000000000000003"]
    assert (r.type, r.amount, r.merchant_raw, r.raw_description, r.source_category) == (
        "transfer", 3000, "Venmo transfer", "Standard Transfer", "Other",
    )


def test_thousands_separators_and_blank_notes():
    rows = by_id(parse())
    assert rows["1000000000000000006"].amount == 125000
    assert rows["1000000000000000008"].raw_description == "Venmo payment"


def test_raw_row_keeps_the_original_row():
    r = by_id(parse())["1000000000000000001"]
    assert r.raw_row["ID"] == "1000000000000000001" and r.raw_row["Amount (total)"] == "- $23.40"


def test_unknown_type_is_flagged_and_kept():
    content = HEADER + b",2000000000000000001,2026-09-01T10:00:00,Weird Thing,Complete,x,A,B,- $3.00\n"
    (r,) = parse(content).rows
    assert (r.type, r.amount, r.flagged) == ("other", 300, True)


def test_repeated_id_in_one_file_is_kept_once():
    row = b",3000000000000000001,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,- $3.00\n"
    assert len(parse(HEADER + row + row).rows) == 1


def test_bad_rows_are_reported_and_the_rest_imported():
    good = b",4000000000000000001,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,- $3.00\n"
    bad_amount = b",4000000000000000002,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,abc\n"
    bad_date = b",4000000000000000003,not-a-date,Payment,Complete,x,Me,Them,- $3.00\n"
    result = parse(HEADER + good + bad_amount + bad_date)
    assert len(result.rows) == 1 and len(result.errors) == 2


def test_wrong_file_is_rejected():
    apple = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()
    with pytest.raises(ValueError, match="Not a Venmo CSV"):
        parse(apple)


def test_fingerprint_uses_the_venmo_id_and_apple_is_unchanged():
    base = dict(transaction_date="2026-09-01", posted_date=None, amount=100, type="purchase",
                raw_description="x", merchant_raw="m", cardholder=None, source_category=None, raw_row={})
    a = RawTransaction(**base, external_id="111")
    same_id_other_details = RawTransaction(**{**base, "amount": 999, "raw_description": "y"}, external_id="111")
    other_id = RawTransaction(**base, external_id="222")
    assert fingerprint(1, a) == fingerprint(1, same_id_other_details)
    assert fingerprint(1, a) != fingerprint(1, other_id)
    assert fingerprint(1, a) != fingerprint(2, a)
    apple = RawTransaction(**base)
    assert fingerprint(1, apple) == fingerprint(1, RawTransaction(**base))
    assert fingerprint(1, apple) != fingerprint(1, a)
```
(Also keep every existing test in `test_merchants_dedup.py` untouched; the Apple fingerprint recipe must not change.)

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_venmo_importer.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.importers.venmo_csv`).

- [ ] **Step 4: Implement**

`backend/finio/importers/base.py`: add `external_id: str | None = None` as the last field of `RawTransaction` (after `flagged`).

`backend/finio/services/dedup.py`:
```python
def fingerprint(account_id: int, r: RawTransaction) -> str:
    if r.external_id:
        parts = [str(account_id), "id", r.external_id]
    else:
        parts = [
            str(account_id), r.transaction_date, r.posted_date or "",
            str(r.amount), r.raw_description,
        ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
```

`backend/finio/importers/venmo_csv.py`:
```python
import csv
import io
import re
from decimal import Decimal, InvalidOperation

from .base import ParseResult, RawTransaction, RowError

REQUIRED_COLUMNS = {"ID", "Datetime", "Type", "Status", "Amount (total)"}
FINAL_STATUSES = {"complete", "issued"}
TRANSFER_TYPES = {"standard transfer", "instant transfer"}
FRIENDS = "Friends & Family"
AMOUNT = re.compile(r"^([+-])\s*\$?\s*([\d,]+(?:\.\d{1,2})?)$")


def _signed_cents(value: str) -> tuple[str, int]:
    """Return the sign ("+" you received, "-" you paid) and the absolute amount in cents."""
    match = AMOUNT.match(value.strip())
    if not match:
        raise ValueError(f"invalid amount: {value.strip()!r}")
    try:
        cents = int((Decimal(match.group(2).replace(",", "")) * 100).to_integral_value())
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {value.strip()!r}") from exc
    return match.group(1), cents


def _find_header(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        cells = {c.strip() for c in row}
        if "ID" in cells and "Datetime" in cells:
            return index
    raise ValueError(f"Not a Venmo CSV; missing columns: {sorted(REQUIRED_COLUMNS)}")


class VenmoCsvImporter:
    def parse(self, content: bytes) -> ParseResult:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
        numbered = [(reader.line_num, row) for row in reader]
        header_at = _find_header([row for _, row in numbered])
        header = [c.strip() for c in numbered[header_at][1]]
        missing = REQUIRED_COLUMNS - set(header)
        if missing:
            raise ValueError(f"Not a Venmo CSV; missing columns: {sorted(missing)}")

        result = ParseResult()
        seen: set[str] = set()
        for line, cells in numbered[header_at + 1:]:
            row = dict(zip(header, cells))
            external_id = (row.get("ID") or "").strip()
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)
            try:
                result.rows.append(self._parse_row(row, external_id))
            except ValueError as exc:
                result.errors.append(RowError(line=line, message=str(exc) or "invalid row"))
        return result

    def _parse_row(self, row: dict, external_id: str) -> RawTransaction:
        get = lambda key: (row.get(key) or "").strip()  # noqa: E731
        status = get("Status")
        if status.lower() not in FINAL_STATUSES:
            raise ValueError(f"status: {status}")
        datetime_text = get("Datetime")
        if not re.match(r"^\d{4}-\d{2}-\d{2}", datetime_text):
            raise ValueError(f"invalid date: {datetime_text!r}")
        sign, cents = _signed_cents(get("Amount (total)"))
        paid = sign == "-"
        amount = cents if paid else -cents

        kind = get("Type")
        lowered = kind.lower()
        note = get("Note")
        if lowered in TRANSFER_TYPES:
            type_, merchant, category, flagged = "transfer", "Venmo transfer", "Other", False
            fallback_note = kind
        else:
            if lowered == "charge":
                counterparty = get("From") if paid else get("To")
            else:
                counterparty = get("To") if paid else get("From")
            merchant, category = counterparty, FRIENDS
            fallback_note = f"Venmo {lowered}" if lowered else "Venmo transaction"
            if lowered in {"payment", "charge"}:
                type_, flagged = ("purchase" if paid else "payment"), False
            else:
                type_, flagged = "other", True

        return RawTransaction(
            transaction_date=datetime_text[:10],
            posted_date=None,
            amount=amount,
            type=type_,
            raw_description=note or fallback_note,
            merchant_raw=merchant,
            cardholder=None,
            source_category=category,
            raw_row={k: v for k, v in row.items() if k},
            flagged=flagged,
            external_id=external_id,
        )
```
Note: `csv.reader.line_num` after a multi-line cell is the last physical line; that is fine for this file. `_parse_row` raises `ValueError` for skipped statuses, which becomes a row error.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS (existing Apple tests included).

- [ ] **Step 6: Commit**

```bash
git add backend/finio/importers backend/finio/services/dedup.py backend/tests/fixtures/venmo_sample.csv backend/tests/test_venmo_importer.py
git commit -m "feat: Venmo CSV importer with ID-based dedup" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Wire Venmo into ingestion, the accounts API and the Accounts page

**Files:**
- Modify: `backend/finio/services/ingestion.py`, `backend/finio/api/accounts.py`, `frontend/src/api.ts`, `frontend/src/pages/Accounts.tsx`
- Create: `backend/tests/test_venmo_ingestion.py`

**Interfaces:**
- Consumes: `VenmoCsvImporter` (Task 1), `import_file(conn, account_id, filename, content)`, the existing `POST /api/accounts` and `POST /api/imports` endpoints.
- Produces: account source `"venmo_csv"` accepted by the API and offered in the UI; `IMPORTERS["venmo_csv"]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_venmo_ingestion.py`:
```python
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
    assert r.status_code == 201 or r.status_code == 200, r.text
    summary = r.json()
    assert (summary["rows_total"], summary["rows_added"], summary["rows_skipped"], summary["flagged"]) == (7, 7, 0, 0)
    assert len(summary["errors"]) == 1                                  # the cancelled payment
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
        b",1000000000000000009,2026-09-17T10:00:00,Payment,Complete,tacos,Test User,Person Five,- $12.00,,0,,0,,\"TEST BANK Checking *0000\",,,,,Venmo,,\n,1000000000000000008,",
    )
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
```
Adjust the exact status codes and JSON keys to what the existing import endpoint really returns (see `backend/tests/test_api_basics.py` `test_import_endpoint_and_error_mapping`, and the `category_rules` column names in `backend/finio/db.py`); keep every assertion's intent. The `insert` of the extra row must produce a valid CSV row with the same column layout as the fixture.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_venmo_ingestion.py -q`
Expected: FAIL (the API rejects `venmo_csv`; no importer registered).

- [ ] **Step 3: Implement**

- `backend/finio/services/ingestion.py`: import `VenmoCsvImporter` and set `IMPORTERS = {"apple_card_csv": AppleCardCsvImporter(), "venmo_csv": VenmoCsvImporter()}`.
- `backend/finio/api/accounts.py`: `source: Literal["apple_card_csv", "venmo_csv", "manual"]`.
- `frontend/src/api.ts`: `export type AccountSource = 'apple_card_csv' | 'venmo_csv' | 'manual'`.
- `frontend/src/pages/Accounts.tsx`: add `<option value="venmo_csv">Venmo CSV import</option>` after the Apple option, and replace the table cell `a.source === 'apple_card_csv' ? 'Apple Card CSV import' : 'Manual entry'` with a small lookup: `{ apple_card_csv: 'Apple Card CSV import', venmo_csv: 'Venmo CSV import', manual: 'Manual entry' }[a.source]`. Also grep the frontend (`Import.tsx` and elsewhere) for any other place that assumes only two sources and update it.
- Check how the Transactions page and filters display a transaction `type` (search `frontend/src` for `'refund'`, `'payment'`, `type`); a `transfer` type must render sensibly (as its own label, no crash). Make the smallest change needed and note it in your report.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q` and `cd ../frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/ingestion.py backend/finio/api/accounts.py backend/tests/test_venmo_ingestion.py frontend/src
git commit -m "feat: Venmo accounts and imports end to end" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, `README.md`, `CLAUDE.md`

**Interfaces:** none. Read each file fully first and match its style and numbering.

- [ ] **Step 1: Update the docs**

- `docs/SPECIFICATION.md`: add the Venmo source: the statement shape, the row mapping table, dedup by Venmo ID, statuses, the new `Friends & Family` category, and that spending counts only `purchase`.
- `docs/REQUIREMENTS.md`: continue the numbering after the last requirement with new requirements: Venmo CSV import; sent payments are spending; received money is money in; bank transfers are not spending; import dedup by transaction ID; non-final statuses are not imported; default category Friends & Family; rules and splits work on Venmo rows.
- `docs/TESTING.md`: add a walkthrough to create a Venmo account and import a small fabricated CSV (give the exact few lines to paste into a file, using fabricated names and IDs), with what to expect on the Transactions page, Dashboard and Insights; mention `tests/test_venmo_*.py`. Never tell testers to use a real statement in the repo.
- `README.md`: one feature bullet for Venmo import. `CLAUDE.md`: mention `importers/venmo_csv.py` in the importers line and the `external_id` dedup rule in the invariants.
- Also fix the spec sentence in the design spec if the implementation differs from it in any way (it should not).

- [ ] **Step 2: Full check**

Run: `cd backend && .venv/bin/pytest -q` and `cd ../frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add docs README.md CLAUDE.md
git commit -m "docs: Venmo import" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| Row mapping (types, signs, counterparty, description, category, dates, cardholder) | 1 |
| Statuses not imported, reported as row errors | 1 |
| Duplicates by Venmo ID, in-file repeat IDs, Apple unchanged | 1 |
| Header/footer/disclaimer skipping, wrong-file error, bad rows | 1 |
| New account source, Accounts page, Import through the API, category created, rules on the note | 2 |
| Spending counts only purchases; transfers and money in excluded | 2 (test), no code change |
| Docs (specification, requirements, testing, README, CLAUDE.md) | 3 |
