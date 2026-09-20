# Finio: Personal Transaction Analyzer — Design

Date: 2026-09-20

## Goal

A local web app on the user's Mac that analyzes Apple Card transactions, Mint-style. Other accounts can be added later. A native Apple app may follow, so core logic lives behind an API and the browser UI is just one client.

## Decisions

- **Ingestion:** Apple Card monthly CSV export (no API exists). PDF is out of scope.
- **Other sources:** manual entry of transactions, with a user-picked category (see Manual entry).
- **Runtime:** local only; FastAPI backend, React + TypeScript (Vite) frontend, SQLite. Data never leaves the machine.
- **Architecture:** layered API with pluggable importers. The raw source row is stored on each imported transaction so parsing and rule changes can be re-applied without re-importing.
- **v1 features:** spending by category over time, search/filter/recategorize, recurring-charge detection, account model with balances stored.
- **Out of scope for v1:** budgets, net-worth view, PDF import, auth, hosting, aggregator (Plaid) sync.

## Apple Card CSV format

Columns: Transaction Date, Clearing Date, Description, Merchant, Category, Type, Amount (USD), Purchased By. Dates are MM/DD/YYYY. Purchases are positive amounts. Apple's categories seen: Entertainment, Grocery, Insurance, Other, Restaurants, Shopping, Transportation, Utilities. Merchant names can contain stray whitespace. `Purchased By` can hold more than one person. There is no transaction ID.

## Data model (SQLite)

- **accounts**: `id`, `name`, `type` (credit_card, checking, savings, other), `source` (importer key such as `apple_card_csv`, or `manual`), `starting_balance`, `starting_balance_date`. Balances are stored; no net-worth view in v1.
- **import_batches**: `id`, `account_id`, `filename`, `file_hash`, `imported_at`, `rows_total`, `rows_added`, `rows_skipped`. Re-importing an identical file is rejected by hash.
- **transactions**:
  - `id`, `account_id`, `batch_id` (null for manual entries)
  - `posted_date`, `transaction_date`
  - `amount` in integer cents; positive means money spent, negative means money in, normalized across sources
  - `type` (purchase, payment, refund, income, other)
  - `raw_description`, `merchant_raw`, `merchant_clean`
  - `cardholder`
  - `category_id`, `category_source` (`source_default`, `rule`, `manual`), `source_category`
  - `origin` (`import` or `manual`)
  - `fingerprint`, `occurrence` (null for manual entries)
  - `raw_row` (JSON of the original CSV row; null for manual entries)
- **Deduplication:** `fingerprint` is a hash of account, transaction date, clearing date, amount, and raw description. `occurrence` counts identical fingerprints within a file. Uniqueness is on `(fingerprint, occurrence)` where fingerprint is not null. Overlapping exports skip stored rows; identical same-day purchases both survive.
- **categories**: `id`, `name`, `parent_id` (optional, one level). Seeded from Apple's labels; user can add and rename. When an imported row carries a category label that matches no existing category (case-insensitive), a category with that label is created and the row keeps it; `Other` is used only when the row has no category label at all. Known limitation: renaming a category does not prevent a later import whose CSV label is the old name from re-creating it (spending then splits across the two names). Re-applying rules has the same effect on existing imported transactions that no rule matches, since they revert to their CSV category. A category-alias mechanism is future work.
- **category_rules**: `id`, `match_field` (merchant or description), `match_type` (contains or equals), `pattern`, `category_id`, `priority`. Applied on import and re-appliable to history. Rules never overwrite `category_source = manual`.
- **merchant_aliases**: `pattern -> clean name`, used to produce `merchant_clean`.
- Recurring charges are computed at query time, not stored.

## Importers and ingestion

- Each importer implements `parse(file) -> list[RawTransaction]`. `RawTransaction` is the normalized shape: dates, integer cents, type, descriptions, cardholder, source category, raw row.
- `AppleCardCsvImporter` is the only importer in v1. It reads `Amount (USD)` and normalizes signs by `Type`. An unrecognized `Type` is imported as `other` and flagged in the summary.
- Ingestion service order: check file hash, parse, clean merchant via aliases, compute fingerprint and occurrence, insert new rows, apply category rules. It returns a summary: added, skipped as duplicates, flagged.
- Malformed rows are reported with line numbers and skipped. The whole import runs in one DB transaction.

## Manual entry

For accounts that have no importer (other banks, cards, websites), the user adds transactions by hand.

- Accounts with `source = manual` can be created in the UI (name and type). Manual transactions can also be added to any account.
- A manual transaction has: account, date, amount, direction (expense, income, or refund), merchant, optional description, optional cardholder, and a **required category picked by the user**.
- Manual transactions are stored with `origin = manual`, `category_source = manual`, and null `batch_id`, `fingerprint`, and `raw_row`. Merchant goes through alias cleaning so recurring detection and search work the same as for imports. Rules do not change a manually chosen category.
- Manual transactions are fully editable and deletable. Imported transactions are read-only except for category (recategorize) and cannot be deleted individually in v1.
- Manual transactions are included in all analytics, filters, and recurring-charge detection.
- The Add Transaction form remembers the last used account and date, and offers merchant autocomplete from existing `merchant_clean` values to speed up entry.
- Validation: amount must be a positive number, date is required and cannot be blank, category must exist. Errors are shown inline.

## API (FastAPI)

- `POST /imports` (file + account), `GET /accounts`, `POST /accounts`
- `GET /transactions`: filters for date range, category, merchant, cardholder, amount range, account, text search; sorting and paging
- `POST /transactions`: create a manual transaction
- `PATCH /transactions/{id}`: recategorize any transaction; edit any field of a manual one
- `DELETE /transactions/{id}`: manual transactions only
- `GET/POST/PATCH/DELETE /categories` and `/rules`; `GET /rules/{id}`; `POST /rules/reapply` (re-derives every non-manual row: rule match, else the source category)
- `GET /analytics/spending-by-category`, `/trends`, `/top-merchants`, `/recurring`. "Spending" excludes payments and refunds by default. Recurring uses an interval and variance heuristic on `merchant_clean`.

## UI (React + TypeScript, Vite)

Screens:
- **Dashboard**: category breakdown, monthly trend, top merchants.
- **Transactions**: search, filters, inline recategorize, "create rule from this", and an **Add transaction** button that opens the manual entry form.
- **Recurring**: detected recurring charges.
- **Import**: drag and drop, with a results summary.
- **Accounts**: list and create accounts, including manual accounts.

A cardholder filter is available throughout.

## Testing and layout

- pytest: importer parsing, dedup and overlap cases, rules and rule priority, manual entry (create, edit, delete, category protection from rules), analytics queries, API tests. Vitest for key UI logic.
- Layout: `backend/` (`importers/`, `services/`, `api/`, `db/`) and `frontend/`. The SQLite file and any real CSVs are git-ignored. Test fixtures use fabricated rows only.

## Open items

None blocking. Decisions deferred beyond v1: budgets, net-worth view, additional importers, native Apple client.
