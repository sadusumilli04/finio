# Finio

Local, private Mint-style analyzer for Apple Card transactions. Imports Apple Card CSV exports, accepts manually entered transactions for other accounts, and shows spending by category, trends, top merchants, and recurring charges. All data stays in a local SQLite file. A native Apple client may come later, so core logic lives behind the API and the browser UI is just one client.

- Spec: `docs/SPECIFICATION.md` (binding design authority)
- Plan: `docs/superpowers/plans/2026-09-20-finio-implementation.md` (task-by-task build order)
- Requirements: `docs/REQUIREMENTS.md`; task summaries: `docs/TASK.md`

## Commands

Backend (Python 3.13, run from `backend/`):
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # first-time setup
.venv/bin/pytest -q                                          # all tests
.venv/bin/pytest tests/test_rules.py -v                      # one file
.venv/bin/uvicorn finio.main:app --port 8000                 # run API
```

Frontend (Node 22, run from `frontend/`; Vite + React + TypeScript):
```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8000
npm test           # Vitest
npx tsc -b         # type-check
npm run build
```

Node here is 22.11, so `vite` ^6, `@vitejs/plugin-react` ^4 and `vitest` ^3 are pinned; do not upgrade to Vite 7/8 (need Node >=22.12) unless Node is upgraded.

The database is `backend/data/finio.sqlite3` (override with the `FINIO_DB` env var).

## Architecture

Layered backend: importers -> services -> FastAPI routes; the React UI calls only `/api`.

- `backend/finio/importers/`: one class per source, `parse(bytes) -> ParseResult` of normalized `RawTransaction`s. Adding an account type means adding an importer and registering it in `services/ingestion.py` `IMPORTERS`.
- `backend/finio/services/`: all business logic (ingestion and dedup, category rules, filters, transactions, analytics, recurring detection). Routes stay thin.
- `backend/finio/api/`: routers, all mounted under `/api` in `app.py`. Domain errors from `finio/errors.py` (`NotFoundError` 404, `ForbiddenError` 403, `ConflictError` 409, `ValidationFailed` 400) are mapped to HTTP responses centrally; raise them from services instead of using `HTTPException`.
- `backend/finio/db.py`: stdlib `sqlite3` with the schema inline, no ORM; schema version tracked in `PRAGMA user_version`; `_migrate` upgrades existing databases (currently to version 2). Connections are per request (`deps.get_conn`).
- `frontend/src/api.ts`: the only place that talks to the backend; pages live in `src/pages/`.

## Conventions and invariants

- Amounts are integer cents. Positive means money spent; negative means money in (payments, refunds, income). Never use floats for money.
- Dates are stored as ISO `YYYY-MM-DD`. Apple CSV dates are `MM/DD/YYYY`.
- "Spending" in analytics counts only `type = 'purchase'`.
- Dedup: Apple CSVs have no transaction ID. Rows are keyed by `(fingerprint, occurrence)` so overlapping exports skip seen rows while identical same-day purchases both survive. Identical files are rejected by hash.
- A manually chosen category (`category_source = 'manual'`) is never overwritten by rules.
- Imported transactions are read-only except category and `my_share`. Only `origin = 'manual'` transactions can be edited or deleted.
- Every imported transaction keeps its original CSV row in `raw_row` so parsing and rules can be re-applied without re-importing.
- Anything that answers "how much did I spend" must use `EFFECTIVE_AMOUNT` from `backend/finio/services/amounts.py` (the user's share when a purchase is split, else the full charge); never re-type the expression or aggregate raw `amount` for spending.
- A purchase can be split (`my_share`, `share_source`): only purchases, `0 <= my_share <= amount`; imported transactions are read-only except category and `my_share`; the charge `amount` is never modified.
- `where_clause()` in `services/filters.py` assumes the transactions table is aliased `t`; every query that uses it must alias accordingly.

## Testing

- pytest for backend (importers, dedup and overlap, rules, manual entry, analytics, API); Vitest for frontend logic.
- Write the failing test first.
- Test fixtures use fabricated rows only (`backend/tests/fixtures/`).

## Data safety

Never commit real financial data. `*.csv` is git-ignored except `backend/tests/fixtures/`. Do not read or copy the user's real statement exports (for example from `~/Downloads`) into the repo, fixtures, or commit messages.

## Out of scope for v1

Budgets, a net-worth view, PDF import, Plaid or other aggregator sync, auth, hosting, and screens for managing categories and merchant aliases (those go through the API).
