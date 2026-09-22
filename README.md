# Finio

A local, private Mint-style analyzer for Apple Card transactions. Import monthly CSV exports (and Venmo statement CSVs), add transactions from other accounts by hand, and see spending by category, trends, top merchants, and recurring charges, plus a monthly Insights page (how the month compares, biggest movers, new merchants, unusual charges, subscription changes). All data stays in a SQLite file on this machine.

Design docs: [docs/SPECIFICATION.md](docs/SPECIFICATION.md), [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md), [docs/TASK.md](docs/TASK.md).

## Setup

```bash
# backend (Python 3.13)
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# frontend (Node 22.11+ works with the committed lockfile)
cd ../frontend
npm ci        # or: npm install
```

The frontend pins `vite` ^6, `@vitejs/plugin-react` ^4 and `vitest` ^3 because Node 22.11 is supported. Vite 7/8 need Node >= 22.12, so do not upgrade them unless Node is upgraded.

## Run

```bash
# terminal 1
cd backend && .venv/bin/uvicorn finio.main:app --port 8000

# terminal 2
cd frontend && npm run dev     # open http://localhost:5173
```

Run uvicorn without `--host` so it stays bound to localhost; that keeps your financial data off the LAN.

The database is created at `backend/data/finio.sqlite3` (override with `FINIO_DB`).

## Use

1. **Accounts**: create an account with source "Apple Card CSV import" (or "Venmo CSV import" for Venmo).
2. **Import**: export a statement CSV from Wallet (Apple Card, Statements) and drop it in. Overlapping exports are safe: rows already stored are skipped, and importing the exact same file twice is rejected. If an imported row's category is not in your category set, that category is created and kept (for example Apple's payment rows create a "Payment" category). `Other` is used only for rows with no category.
3. **Transactions**: recategorize inline, use "Make rule" to categorize a merchant automatically from now on, and use "Add transaction" to enter transactions from other sites by hand. Manual transactions require a category that you pick. Rules recategorize matching existing transactions too, but never override a category you set by hand.
4. **Venmo**: create an account with source "Venmo CSV import" and import a Venmo statement CSV the same way. Money you send counts as spending (category "Friends & Family" by default), money you receive is money in, and bank transfers are not spending. Duplicates are skipped by Venmo transaction ID, and pending or cancelled rows are not imported.
5. **Split a group charge**: open a purchase's ⋯ menu and choose Split… to enter what you actually spent (or split evenly among N people). Only your share counts on the Dashboard; the full charge stays on the transaction.
6. **Insights**: pick a month to see how it compares with the previous one, what changed, and what looks unusual. It needs at least two months of data to say much.
7. **Link Venmo payments to a charge**: on a card charge's ⋯ menu, choose **Link Venmo payments…** to link the friends' Venmo payments that reimbursed it; your share becomes the charge minus what's linked, and unlinking restores the full charge.

## Try it with sample data

`testdata/` has a year of fabricated statements (Jan-Dec 2025) for both sources, for trying the app without your own data: create one account with source "Apple Card CSV import" and one with "Venmo CSV import", then import `testdata/apple_card_2025.csv` and `testdata/venmo_2025.csv` respectively. It has enough spread to show something on the Dashboard, Recurring and Insights pages, including a subscription price change, a missing month, a new merchant and an unusual charge.

## Test

```bash
cd backend && .venv/bin/pytest
cd ../frontend && npm test
```

Never commit real statements: `*.csv` is git-ignored except `backend/tests/fixtures/` and `testdata/`, which hold fabricated rows only.

## Known limitations

- Renaming a category does not stop a later import whose CSV label is the old name from re-creating that old category, so spending then splits across the two names. Re-applying rules (for example after "Make rule") does the same for existing imported transactions: rows that no rule matches go back to their CSV category, which re-creates the old name and moves them out of the renamed one. A category-alias mechanism is future work.
- The dedup fingerprint includes the Clearing Date, so if a transaction's clearing date changes between two exports it can be imported twice.
- There is no undo for an import batch or for a bulk "Make rule" beyond deleting the rule and re-applying rules (which restores source categories).
