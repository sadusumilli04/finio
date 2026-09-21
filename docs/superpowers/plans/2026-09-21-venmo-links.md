# Venmo Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user link incoming Venmo payments to an Apple Card (non-Venmo) charge so the charge's "my share" becomes the charge minus the linked payments.

**Architecture:** A `venmo_links` table (one row per linked Venmo payment) and a service `services/venmo_links.py` that validates, inserts or deletes links and recalculates `my_share` (`share_source = 'venmo'`) through the existing split columns. Four endpoints under `/api/transactions/{id}`; a `VenmoLinkPanel` component beside the Split panel. Analytics and insights already use the user's share and are unchanged.

**Tech Stack:** Python 3.13, FastAPI, sqlite3, pytest; React + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-21-venmo-links-design.md` (binding).

## Global Constraints

- Work on branch `venmo-links` in the main project folder. No git worktrees. Do not push, open PRs or merge.
- Amounts are integer cents (positive = spent, negative = money in). A Venmo payment in is stored negative; the amount reimbursed is `abs(amount)`.
- Domain errors from `finio/errors.py` (`NotFoundError` 404, `ConflictError` 409, `ValidationFailed` 400); never `HTTPException` in services. Routes stay thin.
- The window for candidates is a named constant in the service module, not a literal in a query.
- Every query on transactions that uses `where_clause()` aliases the table `t`. Do not change analytics or insights code.
- The existing split rules hold: only purchases can have a share, `0 <= my_share <= amount`, `my_share` and `share_source` are NULL together.
- Never commit real financial data; test data is fabricated. Do not read `backend/data/` or any real statement.
- Docs live in `docs/` (README.md and CLAUDE.md stay at the root). Vite ^6 stays pinned; type-check with `./node_modules/.bin/tsc -b`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## File Structure

- Modify `backend/finio/db.py` (table, `SCHEMA_VERSION = 3`), `backend/finio/services/transactions.py` (list fields, refusals), `backend/finio/services/accounts.py` (delete cleanup), `backend/finio/api/transactions.py` (endpoints).
- Create `backend/finio/services/venmo_links.py`, `backend/tests/test_venmo_links.py`, `backend/tests/test_venmo_links_api.py`.
- Frontend: modify `frontend/src/api.ts`, `frontend/src/pages/Transactions.tsx`, `frontend/src/components/SplitPanel.tsx`, `frontend/src/styles.css`; create `frontend/src/components/VenmoLinkPanel.tsx`, `frontend/src/lib/venmoLinks.ts` (+ test).
- Docs: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, `README.md`, `CLAUDE.md`.

---

### Task 1: Backend — links table, service, refusals, endpoints

**Files:** as listed under Backend above.

**Interfaces:**
- Produces (`services/venmo_links.py`):
  - `CANDIDATE_DAYS_BEFORE = 3`, `CANDIDATE_DAYS_AFTER = 30`
  - `list_candidates(conn, charge_id) -> list[dict]` — items `{"id", "date", "merchant", "description", "amount"}`; `amount` positive cents.
  - `list_links(conn, charge_id) -> list[dict]` — same item shape, for payments linked to the charge, oldest date first.
  - `link_payment(conn, charge_id, venmo_transaction_id) -> dict` — returns `get_transaction(conn, charge_id)`.
  - `unlink_payment(conn, charge_id, venmo_transaction_id) -> dict` — returns `get_transaction(conn, charge_id)`; `NotFoundError` when that payment is not linked to that charge.
  - `is_linked(conn, charge_id) -> bool`, and `recalculate_share(conn, charge_id) -> None` (used internally and by account deletion).
- Table (in `SCHEMA`):
  ```sql
  CREATE TABLE IF NOT EXISTS venmo_links (
      venmo_transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id),
      card_transaction_id INTEGER NOT NULL REFERENCES transactions(id)
  );
  CREATE INDEX IF NOT EXISTS ix_venmo_links_card ON venmo_links(card_transaction_id);
  ```
  `SCHEMA_VERSION = 3` (existing databases get the table from `SCHEMA` since it uses `IF NOT EXISTS`; add a test that an old-format DB without the table gains it on `init_db`; update any test asserting the old version).
- Transaction reads (`TXN_SELECT` in `services/transactions.py`) gain two columns: `(SELECT COUNT(*) FROM venmo_links l WHERE l.card_transaction_id = t.id) AS venmo_link_count` and `(SELECT l.card_transaction_id FROM venmo_links l WHERE l.venmo_transaction_id = t.id) AS venmo_linked_to`.
- Refusals in `services/transactions.py`: when a charge has links (`is_linked`), `set_share(...)` with `source == 'manual'` and `update_transaction` fields `my_share`, `amount`, `direction` raise `ValidationFailed("Unlink the Venmo payments first")`. (`recalculate_share` writes the columns directly, not through those functions, so it is not refused; `set_share(..., 'venmo')` is not refused.)
- Endpoints in `api/transactions.py` (thin, use the service):
  - `GET /transactions/{id}/venmo-candidates` → `list_candidates`
  - `GET /transactions/{id}/venmo-links` → `list_links`
  - `POST /transactions/{id}/venmo-links` body `{"venmo_transaction_id": int}` → `link_payment` (status 200, returns the charge)
  - `DELETE /transactions/{id}/venmo-links/{venmo_transaction_id}` → `unlink_payment` (returns the charge)
  Define the routes so they do not clash with the existing `/transactions/{id}` routes.

Behavior of `link_payment` (validate in this order): charge exists (404) → is a `purchase` on an account whose source is not `venmo_csv` (400 "Only a purchase on a non-Venmo account can be linked") → payment exists (404) → is a `payment` on a `venmo_csv` account (400 "Only an incoming Venmo payment can be linked") → not already linked anywhere (409 "This Venmo payment is already linked") → `existing_total + abs(payment.amount) <= charge.amount` (400 "The linked payments would exceed the charge"). Then insert and `recalculate_share` in one transaction (`with conn:`).
`recalculate_share`: `total = sum(abs(amount))` of linked payments; if `total == 0`: clear `my_share`/`share_source` only when `share_source == 'venmo'`; else set `my_share = amount - total`, `share_source = 'venmo'`.
`list_candidates`: incoming Venmo payments (`type='payment'`, account source `venmo_csv`, not in `venmo_links`) with `transaction_date` between `charge_date - CANDIDATE_DAYS_BEFORE` and `charge_date + CANDIDATE_DAYS_AFTER` (use `date`/`timedelta` in Python and bind ISO strings), ordered by absolute day distance from the charge date, then larger amount first, then id. Raises the same 404/400 as link for the charge.
`accounts.delete_account`: before deleting transactions, delete `venmo_links` rows whose Venmo payment or card charge belongs to the account, and afterwards `recalculate_share` for each surviving charge that lost a link (collect their ids first).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_venmo_links.py` (service level, using the `conn`, `make_account` fixtures and `tests.helpers.insert_txn`; add a small local helper `venmo(conn)` that creates an account via `make_account(source="venmo_csv", name="Venmo", type="other")`):
```python
import pytest

from finio.errors import ConflictError, NotFoundError, ValidationFailed
from finio.services import transactions as tx
from finio.services.accounts import delete_account
from finio.services.venmo_links import link_payment, list_candidates, list_links, unlink_payment


def setup(conn, make_account):
    card = make_account()
    venmo = make_account(source="venmo_csv", name="Venmo", type="other")
    return card, venmo


def charge(conn, card, amount=18000, date="2026-09-10"):
    return insert_txn(conn, card, date=date, amount=amount, merchant="Dinner Place", category="Restaurants")


def payin(conn, venmo, amount=4500, date="2026-09-11", who="Person One"):
    return insert_txn(conn, venmo, date=date, amount=-amount, type="payment", merchant=who, description="dinner")
```
(import `insert_txn` from `tests.helpers`.) Cases, each a test with concrete assertions:
1. Linking one $45 payment to a $180 charge → charge `my_share == 13500`, `share_source == 'venmo'`, `venmo_link_count == 1`; the payment's read has `venmo_linked_to == charge_id`.
2. Three $45 payments → `my_share == 4500`; unlinking one → `my_share == 9000`; unlinking all → `my_share is None` and `share_source is None`.
3. Refuses: linking to a non-purchase or to a charge on the Venmo account (400); linking a Venmo purchase (a payment you sent) or a card transaction as the payment (400); linking an already-linked payment to another charge (409, and the first link untouched); linking that would exceed the charge (400, share unchanged); missing ids (404); unlinking a payment that is not linked to that charge (404).
4. A manual share on the charge is replaced by linking (`share_source` becomes `'venmo'`); after unlinking all, the share is cleared (not restored).
5. While linked: `tx.set_share(conn, id, 100)` and `tx.update_transaction(conn, id, {"my_share": 100})` and (manual-origin charge) `{"amount": 20000}` raise `ValidationFailed` with "Unlink the Venmo payments first"; recategorizing still works.
6. `list_candidates`: only unlinked incoming Venmo payments dated within 3 days before to 30 days after the charge date (boundaries: day −3 and day +30 included, −4 and +31 excluded), other-account payments and Venmo purchases excluded, ordered closest first then larger amount; a linked payment disappears from candidates and appears in `list_links`.
7. `delete_account` of the Venmo account removes links and clears the venmo-sourced share; deleting the card account removes links and leaves the Venmo payments unlinked.
8. Dashboard total reflects the share: after linking, `analytics.spending_by_category(conn)` for Restaurants equals `13500` (use `finio.services.analytics.spending_by_category`).
9. `init_db` on an old database that lacks `venmo_links` creates the table (build an old DB by dropping the table, then call `init_db`), and `PRAGMA user_version` is 3.

`backend/tests/test_venmo_links_api.py` (with the `client`, `conn`, `make_account` fixtures): the four endpoints end to end — candidates list shape (`id, date, merchant, description, amount`), POST returns the charge with `my_share`, `share_source`, `venmo_link_count`; DELETE returns the charge; status codes 404/409/400 with the messages; `GET /api/transactions` items include `venmo_link_count` and `venmo_linked_to`; `PATCH`/update of `my_share` on a linked charge returns 400 (use the existing transaction update route; find it in `api/transactions.py`).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_venmo_links.py tests/test_venmo_links_api.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.venmo_links`).

- [ ] **Step 3: Implement**

Implement the table, `TXN_SELECT` columns, service, refusals, endpoints and the account-deletion cleanup as described above. Keep the service functions small; reuse `get_transaction` from `services/transactions.py` (import inside the function or arrange imports to avoid a cycle: `transactions.py` needs `is_linked`, so put `is_linked` in `venmo_links.py` and import it lazily inside the refusing functions, or put the tiny link-count query in `transactions.py` and have `venmo_links.py` import from it).

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: link Venmo payments to card charges" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Frontend — link panel

**Files:** `frontend/src/api.ts`, `frontend/src/components/VenmoLinkPanel.tsx`, `frontend/src/lib/venmoLinks.ts`, `frontend/src/lib/venmoLinks.test.ts`, `frontend/src/pages/Transactions.tsx`, `frontend/src/components/SplitPanel.tsx`, `frontend/src/styles.css`.

**Interfaces:**
- Consumes: the endpoints from Task 1; `Transaction` type; `RowMenu`, `SplitPanel` patterns; `formatCents`.
- Produces:
  - `api.ts`: `Transaction` gains `venmo_link_count: number` and `venmo_linked_to: number | null`; `type VenmoPayment = { id: number; date: string; merchant: string; description: string; amount: number }`; `api.venmoCandidates(id)`, `api.venmoLinks(id)`, `api.linkVenmo(id, venmoId): Promise<Transaction>`, `api.unlinkVenmo(id, venmoId): Promise<Transaction>` (request helper style as in the file).
  - `lib/venmoLinks.ts`: `shareAfterLinks(charge: number, reimbursed: number[]): number` (charge minus the sum, never below 0), `wouldExceed(charge: number, reimbursed: number[], next: number): boolean`, `linkSummary(charge: number, reimbursed: number[]): string` → `"Your share: $45.00 of $180.00"`. Vitest tests for each (boundaries: exactly equal is fine, one cent over exceeds, empty list).
  - `VenmoLinkPanel` (props `{ transaction: Transaction; onDone: (updated: Transaction) => void; onCancel: () => void }`): loads linked payments and candidates (loading and error states; errors from link/unlink shown in the panel, buttons disabled while busy), renders linked payments each with an **Unlink** button, candidates each with a **Link** button (date, person, note, amount; a candidate that would exceed the charge is disabled with a short reason), the resulting share line, and, when `transaction.share_source === 'manual'`, the note "Linking replaces your manual split". After each successful link/unlink it calls `onDone(updated)` with the returned charge AND refreshes its own lists; a Close button calls `onCancel`.
  - `Transactions.tsx`: the row menu gets **Link Venmo payments…** only for purchases on a non-Venmo account (use `account_name`/account data already on the page; if the row lacks the account source, add `account_source` to `TXN_SELECT` and the `Transaction` type in this task, with a backend test that the list includes it); it opens the panel the same way the Split panel opens (mutually exclusive with it). A charge with `venmo_link_count > 0` shows a small **Venmo-linked** tag; a Venmo row with `venmo_linked_to` set shows **linked to <merchant of that charge, or “a charge” if unknown>** (a simple "linked" tag is acceptable if the merchant is not readily available).
  - `SplitPanel.tsx`: when `t.venmo_link_count > 0`, show "This split comes from linked Venmo payments. Unlink them to change it." and disable the form's inputs and Save.
  - Scoped CSS under the existing transactions-page scope, matching the Split panel's styles.

- [ ] **Step 1: Write the failing tests** for `lib/venmoLinks.ts` and the `api.ts` calls (extend `api.test.ts`: the four request URLs and methods, using the file's existing fetch stub).
- [ ] **Step 2: Run to verify failure:** `cd frontend && npm test -- --run`.
- [ ] **Step 3: Implement** the types, helpers, panel, page and split-panel changes and styles.
- [ ] **Step 4: Verify:** `cd frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build` (all pass). No browser harness exists; the browser check is done by the controller.
- [ ] **Step 5: Commit**

```bash
git add frontend backend
git commit -m "feat: Venmo link panel on the Transactions page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs

**Files:** `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `docs/TESTING.md`, `README.md`, `CLAUDE.md`.

- [ ] **Step 1:** Read each file fully and match style and numbering. `SPECIFICATION.md`: the links model, rules, the four endpoints, list fields, the UI. `REQUIREMENTS.md`: continue the numbering with requirements for linking, share recalculation, refusals, unlinking, candidates, account deletion. `TESTING.md`: a walkthrough with a FABRICATED example (a card charge plus three incoming Venmo payments; expected shares) using a small fabricated Venmo CSV; mention `tests/test_venmo_links*.py`. `README.md`: one bullet. `CLAUDE.md`: invariants — a linked charge's split is derived from its links (`share_source = 'venmo'`), and manual split/amount edits are refused while linked.
- [ ] **Step 2:** Full check: `cd backend && .venv/bin/pytest -q`; `cd ../frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build`.
- [ ] **Step 3: Commit**

```bash
git add docs README.md CLAUDE.md
git commit -m "docs: Venmo links" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| Storage and derived share, rules, refusals, candidates window, account deletion | 1 |
| API (four endpoints, list fields) | 1 |
| UI (panel, tags, Split panel note, manual-split warning, errors) | 2 |
| Testing, docs | 1, 2, 3 |
