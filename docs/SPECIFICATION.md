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
- **Out of scope for v1:** budgets, net-worth view, PDF import, auth, hosting, aggregator (Plaid) sync, Venmo integration, per-person split amounts, tracking money owed.

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
  - `my_share` (integer cents, nullable; the part of a purchase that was the user's, null when unsplit, `0 <= my_share <= amount`) and `share_source` (`manual`, or `venmo`, reserved for a later Venmo importer; null together with `my_share`). The effective amount is `COALESCE(my_share, amount)`, defined once in `backend/finio/services/amounts.py`. The charge `amount` is never modified, so the app keeps matching the statement.
- **Deduplication:** `fingerprint` is a hash of account, transaction date, clearing date, amount, and raw description. `occurrence` counts identical fingerprints within a file. Uniqueness is on `(fingerprint, occurrence)` where fingerprint is not null. Overlapping exports skip stored rows; identical same-day purchases both survive.
- **categories**: `id`, `name`, `parent_id` (optional, one level). Seeded from Apple's labels; user can add and rename. When an imported row carries a category label that matches no existing category (case-insensitive), a category with that label is created and the row keeps it; `Other` is used only when the row has no category label at all. Known limitation: renaming a category does not prevent a later import whose CSV label is the old name from re-creating it (spending then splits across the two names). Re-applying rules has the same effect on existing imported transactions that no rule matches, since they revert to their CSV category. A category-alias mechanism is future work.
- **category_rules**: `id`, `match_field` (merchant or description), `match_type` (contains or equals), `pattern`, `category_id`, `priority`. Applied on import and re-appliable to history. Rules never overwrite `category_source = manual`.
- **merchant_aliases**: `pattern -> clean name`, used to produce `merchant_clean`.
- Recurring charges are computed at query time, not stored.
- **Schema version:** `PRAGMA user_version` is 2. Version 2 adds `my_share` and `share_source`; `init_db` adds any missing columns to an existing database (by column presence, so databases stamped 0 or 1 also migrate) and never lowers the version.

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
- Manual transactions are fully editable and deletable. Imported transactions are read-only except for category (recategorize) and my share (split) and cannot be deleted individually in v1.
- Manual transactions are included in all analytics, filters, and recurring-charge detection.
- The Add Transaction form remembers the last used account and date, and offers merchant autocomplete from existing `merchant_clean` values to speed up entry.
- Validation: amount must be a positive number, date is required and cannot be blank, category must exist. Errors are shown inline.

## API (FastAPI)

- `POST /imports` (file + account), `GET /accounts` (each with its `transaction_count`), `POST /accounts`, `DELETE /accounts/{id}` (deletes the account together with its transactions and import history, atomically; 404 if unknown)
- `GET /transactions`: filters for date range, category, merchant, cardholder, amount range, account, text search; sorting and paging
- `POST /transactions`: create a manual transaction
- `PATCH /transactions/{id}`: recategorize any transaction; edit any field of a manual one. `my_share` (integer cents, or `null` to clear) sets or removes a split on any purchase, imported rows included; the other fields of an imported row stay read-only. The share must satisfy `0 <= my_share <= amount`, and only purchases can be split (400 otherwise). Setting a share records `share_source = manual`. Editing a manual transaction that has a split: lowering its amount below the existing share is rejected (400, "The split exceeds the new charge; edit the split first"); changing its direction to income or refund clears the split; and when an amount and a `my_share` are sent together, the share is validated against the new amount.
- `DELETE /transactions/{id}`: manual transactions only
- `GET/POST/PATCH/DELETE /categories` and `/rules`; `GET /rules/{id}`; `POST /rules/reapply` (re-derives every non-manual row: rule match, else the source category)
- Every transaction object carries `my_share`, `share_source` and `effective_amount` (cents). `sort=amount`, `min_amount` and `max_amount` on `GET /transactions` use the effective amount.
- `GET /analytics/spending-by-category`, `/trends`, `/top-merchants`, `/recurring`. "Spending" excludes payments and refunds by default, and counts the user's share (the effective amount) of each purchase; purchases whose share is 0 are left out of spending, trends, top merchants and recurring, but stay in the transaction list. Recurring uses an interval and variance heuristic on `merchant_clean`.
- `GET /analytics/top-merchants` also takes `limit` (1-100, default 10) and `sort`: `spent` (default, most spent first, ties by name) or `visits` (most transactions first, ties by total spent, then name); any other value is rejected. Every analytics endpoint accepts the filters `date_from`, `date_to`, `account_id`, `cardholder` and `category_id`.
- `GET /insights?month=YYYY-MM&cardholder=NAME` (`month` and `cardholder` optional; an empty or missing `cardholder` means everyone): the monthly insights, computed by `backend/finio/services/insights/` (thresholds in its `constants.py`). Amounts are cents and count the user's share, like all spending. With `cardholder`, every insight (including `available_months`, the typical month, the rank, the recurring-charge detection and the category history behind unusual charges) uses only that person's purchases, and the default month is chosen from that person's months; a cardholder with no spending gets a normal 200 response with `available_months` empty. The response has `month`, `in_progress`, `as_of`, `days_elapsed`, `days_in_month`, `available_months` (every month with spending, ascending, excluding months after the current month) and:
  - `summary`: `total`, `compared_with` (for example "Aug 1–20"), `previous_total`, `change`, `change_pct` (null when the previous total is 0), `typical_total` (median of the other complete months, null under 3), `rank` (`{position, of}` among complete months, null unless M is complete and there are 3 or more), `projected_total` (in-progress month from day 7, else null).
  - `movers`: `up` and `down`, up to 3 each, of `category`, `category_id`, `current`, `previous`, `change`, `change_pct`; changes under $10 are ignored.
  - `new_merchants`: `merchant`, `total`, `count`; merchants with no earlier spending, empty when the month is the earliest.
  - `growing_merchants`: `merchant`, `current`, `previous`, `change`, `change_pct`; up by at least $25 and 1.5x.
  - `unusual_charges`: `transaction_id`, `date`, `merchant`, `category`, `amount`, `typical`; at least 3x the category's earlier median and $50, with at least 5 earlier purchases in the category.
  - `subscriptions`: monthly recurring merchants only; `merchant`, `kind` (`missing`, `price_up`, `price_down`, `new`), `current`, `previous`, `expected_date` (only for `missing`).
  - An in-progress month (the current calendar month) is compared with the same days of the previous month, never with a full month. When `month` is omitted it defaults to the current month if it has spending, else the latest month with spending, else the current month with an empty result. A malformed month or a month after the current one returns 400; a valid month with no spending returns an empty result. A null field means not enough history; lists are empty when nothing qualifies.

## UI (React + TypeScript, Vite)

Screens:
- **Dashboard**: category breakdown, monthly trend, top merchants. Filters (date range with one-click presets, cardholder, account, category) apply to every section. Top merchants lets the user choose how many to show (5, 10, 25 or 50) and rank them by most spent or most visits.
- **Transactions**: search, filters, inline recategorize, "create rule from this", an **Add transaction** button that opens the manual entry form, and a **Split panel**. A purchase's ⋯ menu offers **Split…** (or **Edit split…** and **Remove split** once split); the panel shows the charge, an "even split among N people" shortcut with **Fill in**, an exact **My share** amount (0 is allowed), and the live "Paid for others" figure. A split row shows the user's share in bold with the full charge beneath it ("of $120.00"); the amount column, sort and amount filters use the effective amount. The Dashboard has no new controls; its numbers reflect the share.
- **Insights**: a nav item after Dashboard, at `/insights`. A **Person** dropdown ("Everyone" plus each cardholder) beside a month picker (months with spending, newest first, the current one labelled "in progress") with previous/next arrows. A **Month at a glance** card with the total ("so far" while in progress), the change against the compared days in words ("Up $212.00 (+12%) vs Aug 1–20"), the typical month, the rank, and for an in-progress month the day count and pace. Five cards: Biggest movers (went up / went down), New merchants, Merchants that grew, Unusual charges, and Subscription changes (tags Price up, Price down, New, Missing). Each card has a one-line note on how it is computed and its own empty message. States: an error alone, then "Loading…", then the content dimmed while refetching; with no data the page says "Import a statement to see insights", or "No spending for this person" when a person is chosen. Changing the person keeps the selected month if that person has spending in it, otherwise the page jumps to their default month.
- **Recurring**: detected recurring charges.
- **Import**: drag and drop, with a results summary.
- **Accounts**: list, create and delete accounts, including manual accounts. Deleting asks for confirmation and states how many transactions will be removed.

A cardholder filter is available throughout.

## Testing and layout

- pytest: importer parsing, dedup and overlap cases, rules and rule priority, manual entry (create, edit, delete, category protection from rules), analytics queries, API tests. Vitest for key UI logic.
- Layout: `backend/` (`importers/`, `services/`, `api/`, `db/`) and `frontend/`. The SQLite file and any real CSVs are git-ignored. Test fixtures use fabricated rows only.

## Open items

None blocking. Decisions deferred beyond v1: budgets, net-worth view, additional importers, native Apple client.
