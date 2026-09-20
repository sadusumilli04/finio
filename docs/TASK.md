# Finio build tasks

A short explanation of each of the 16 tasks in the implementation plan (`docs/superpowers/plans/2026-09-20-finio-implementation.md`). Tasks 1–11 build the backend, 12–15 build the UI, and 16 wraps up. Each task follows test first, then code, then commit, and ends with something you can run.

## Backend

1. **Backend scaffold, schema, seed data.** Sets up the Python project, the SQLite schema (accounts, import batches, transactions, categories, rules, merchant aliases), the eight seeded categories, and the shared test fixtures. Everything else builds on this.
2. **Apple Card CSV importer.** Parses Apple's statement export into a common transaction shape: MM/DD/YYYY dates become ISO, dollar amounts become integer cents, and payments and refunds are made negative. Bad rows are reported with line numbers instead of failing the whole file.
3. **Merchant cleaning and dedup helpers.** Tidies messy merchant names (extra whitespace, user-defined aliases) and computes a fingerprint plus an occurrence counter per row. Apple's CSV has no transaction ID, so this is how overlapping exports avoid double-counting while two identical same-day purchases both survive.
4. **Category rules engine.** Lets a rule like "merchant contains Target -> Grocery" assign categories, with priorities. Falls back to Apple's category, then `Other`. Rules can be re-applied to history but never overwrite a category you chose by hand.
5. **Ingestion service.** Ties the pieces together into one import: reject a file already imported, parse, clean, dedup, categorize, and store, all in a single database transaction. Returns a summary of rows added, skipped as duplicates, and flagged. Keeps the original CSV row on each transaction.
6. **API app, accounts, categories, imports.** Creates the FastAPI app under `/api`, maps domain errors to HTTP status codes in one place, and adds the endpoints for accounts, categories, and uploading a CSV.
7. **Transaction listing and filters.** `GET /api/transactions` with filters (dates, category, merchant, cardholder, amount, text search), sorting, and paging, plus lists of cardholders and merchants for the UI's dropdowns and autocomplete.
8. **Manual transactions.** Add transactions by hand for accounts with no importer: pick the account, date, amount, expense/income/refund, merchant, and a required category. Manual rows can be edited and deleted; imported rows can only be recategorized.
9. **Rules and merchant alias API.** Endpoints to create, edit, and delete category rules and merchant aliases, plus "re-apply rules" to recategorize existing transactions.
10. **Spending analytics.** Spending by category, monthly trends, and top merchants. Counts purchases only, so payments and refunds don't inflate spending.
11. **Recurring-charge detection.** Finds subscriptions and other repeating charges (weekly, biweekly, monthly, yearly) by looking for at least three charges at regular intervals with similar amounts, and predicts the next expected date.

### Follow-up to Tasks 4 and 5

**Unknown CSV categories.** Added after the plan was written: when an imported row's category isn't in your set, the app creates that category and keeps it on the row instead of falling back to `Other`. `Other` is used only when the row has no category label.

## Frontend

12. **Frontend scaffold and helpers.** Creates the Vite + React + TypeScript app with a proxy to the backend, and tested helpers for formatting money, parsing amounts typed by the user, building query strings, and fetching data.
13. **API client, app shell, Accounts and Import screens.** A typed client for every endpoint, the navigation shell, an Accounts page (create Apple Card and manual accounts), and an Import page with drag and drop and a results summary.
14. **Transactions screen and manual entry form.** The main table with search, filters, inline recategorizing, "Make rule" for a merchant, and an Add transaction form (with edit and delete for manual rows) that remembers your last account and date and autocompletes merchants.
15. **Dashboard and Recurring screens.** The Mint-style overview (spending by category, monthly trend, top merchants) and a table of detected recurring charges, both with date, cardholder, and account filters.

## Wrap-up

16. **README and end-to-end smoke test.** Documents setup, running, and usage, then exercises the running app with fabricated data: import, duplicate rejection, dashboard totals, manual entry, recategorizing, and rules.
