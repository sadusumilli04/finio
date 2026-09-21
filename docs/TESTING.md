# Testing Finio locally

This guide is for developers who clone the repo and want to test it: run the automated tests, try the app with safe sample data, and report what they find. It takes about 15 minutes for the setup and the walkthrough.

Commands are for macOS and Linux. On Windows, adjust the paths (`.venv\Scripts\...`) and set environment variables in your shell's own way.

> **Use only the fabricated sample data.** Finio is built for real bank statements, and real financial data must never go into this repo, an issue, or a screenshot. Everything below uses `backend/tests/fixtures/apple_sample.csv`, which contains made-up rows.

## What you need

- Git
- Python 3.13
- Node 22 (22.11 is what the project is developed on; the lockfile pins Vite 6 for that reason, so don't upgrade it)
- Optional: `curl` for the API checks, `sqlite3` to look inside the database

## 1. Set up

The repository is private on GitHub, so ask the owner to give you access before you clone it.

```bash
git clone https://github.com/sadusumilli04/finio.git
cd finio

# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# frontend
cd ../frontend
npm ci
```

## 2. Run the automated tests

```bash
cd backend && .venv/bin/pytest -q          # backend: importer, dedup, rules, splits, analytics, API
cd ../frontend && npm test                 # frontend: helpers (money, dates, filters, splits, ...)
npm run build                              # type-checks (tsc) and builds the frontend
```

Everything should pass. Warnings from third-party libraries in the pytest summary are expected. If a test fails on a fresh clone, that's a bug worth reporting (see [Reporting a bug](#reporting-a-bug)).

## 3. Run the app with a throwaway database

Use your own database file so you never touch anyone's real data, and so you can delete it to start over. Run the two servers in two terminals:

```bash
# terminal 1: backend on http://127.0.0.1:8000
cd backend
FINIO_DB=/tmp/finio-test.sqlite3 .venv/bin/uvicorn finio.main:app --port 8000

# terminal 2: frontend on http://localhost:5173
cd frontend
npm run dev
```

Open http://localhost:5173. Leave `--host` off the backend command so it stays reachable only from your machine.

To reset, stop the backend and delete `/tmp/finio-test.sqlite3`. The next start creates a fresh, empty database.

## 4. The sample data

`backend/tests/fixtures/apple_sample.csv` has six made-up Apple Card rows:

| Date | Merchant | Amount | Apple's category | Cardholder |
|---|---|---|---|---|
| Sep 18, 2026 | Target | $29.77 | Grocery | Test Person A |
| Sep 18, 2026 | Flik Cafe Az Qps | $10.44 | Restaurants | Test Person B |
| Sep 17, 2026 | Blue Bottle | $5.00 | Restaurants | Test Person A |
| Sep 17, 2026 | Blue Bottle (a second, identical purchase) | $5.00 | Restaurants | Test Person A |
| Sep 16, 2026 | Payment | -$100.00 | Payment | Test Person A |
| Sep 15, 2026 | Netflix | $15.49 | Entertainment | Test Person A |

After you import it, these are the numbers to expect. The Dashboard counts purchases only, so the payment is left out:

- **Total spending:** $65.70
- **By category:** Grocery $29.77 (45.3%), Restaurants $20.44 (31.1%), Entertainment $15.49 (23.6%)
- **Top merchants:** Target $29.77, Netflix $15.49, Flik Cafe Az Qps $10.44, Blue Bottle $10.00 (2 transactions)
- **Categories:** the eight defaults plus a new **Payment** category, created from the payment row
- **Monthly trend:** one month (2026-09) at $65.70. There is no median line, because that needs at least two months.
- **Recurring:** empty. It needs at least three similar charges at a regular interval.

The sample is dated September 2026. On the Dashboard, the "This month" and "Last month" buttons only show it if today's date falls in the right month, so use the From and To fields (`2026-09-01` to `2026-09-30`) or leave the dates empty.

## 5. Quick API check (2 minutes)

This exercises the backend without the UI. Run it from the repo root while the backend is running. It creates an account, imports the sample, and tries splits.

```bash
BASE=http://127.0.0.1:8000/api

# 1. create an Apple Card account
curl -s -X POST $BASE/accounts -H 'Content-Type: application/json' \
  -d '{"name":"Apple Card","type":"credit_card","source":"apple_card_csv"}'
# -> {"id":1,"name":"Apple Card",...,"transaction_count":0}

# 2. import the sample (use the id from step 1)
curl -s -F account_id=1 -F file=@backend/tests/fixtures/apple_sample.csv $BASE/imports
# -> {"batch_id":1,"rows_total":6,"rows_added":6,"rows_skipped":0,"flagged":0,"errors":[]}

# 3. import the same file again: rejected as a duplicate
curl -s -w ' [HTTP %{http_code}]\n' -F account_id=1 -F file=@backend/tests/fixtures/apple_sample.csv $BASE/imports
# -> {"detail":"This exact file was already imported for this account"} [HTTP 409]

# 4. spending by category (amounts are in cents): Grocery 2977, Restaurants 2044, Entertainment 1549
curl -s $BASE/analytics/spending-by-category

# 5. split the Target purchase (transaction 1) so only $14.89 of its $29.77 is yours
curl -s -X PATCH $BASE/transactions/1 -H 'Content-Type: application/json' -d '{"my_share":1489}'
# -> amount 2977, my_share 1489, share_source "manual", effective_amount 1489
#    total spending is now 5082 instead of 6570

# 6. a share above the charge, and a split on the payment (transaction 5), are both rejected
curl -s -w ' [HTTP %{http_code}]\n' -X PATCH $BASE/transactions/1 -H 'Content-Type: application/json' -d '{"my_share":9999}'
# -> {"detail":"Your share must be between $0.00 and the charge"} [HTTP 400]
curl -s -w ' [HTTP %{http_code}]\n' -X PATCH $BASE/transactions/5 -H 'Content-Type: application/json' -d '{"my_share":100}'
# -> {"detail":"Only purchases can be split"} [HTTP 400]

# 7. remove the split, then delete the account (deletes its transactions and import history too)
curl -s -X PATCH $BASE/transactions/1 -H 'Content-Type: application/json' -d '{"my_share":null}'
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $BASE/accounts/1
# -> 204
```

The API also lists its own endpoints at http://127.0.0.1:8000/docs.

## 6. Manual walkthrough in the browser

Work through these in order on an empty database. "Expect" is what should happen; anything else is worth reporting.

**Accounts and import**
1. **Accounts** page → add an account named "Apple Card", type Credit card, source "Apple Card CSV import". Expect it in the table with 0 transactions.
2. **Import** page → choose that account and drop in `apple_sample.csv`. Expect "6 added, 0 skipped as duplicates".
3. Import the same file again. Expect a clear error that it was already imported, and no change to the data.
4. Try importing a file that is not an Apple Card CSV (for example a text file renamed to `.csv`). Expect an error message, not a crash or a blank screen.

**Transactions**
5. **Transactions** page. Expect six rows, newest first. The payment shows as green -$100.00, and each row has a category color dot.
6. Search for `blue`. Expect the two Blue Bottle rows.
7. Open **Filters**, pick cardholder "Test Person B". Expect one row, a "Cardholder: Test Person B" chip, and a "1" badge on the Filters button. Remove the chip with its ×, then try **Clear all**.
8. Sort by "Largest first" and "Smallest first". Expect the order to follow the amounts (the payment counts as negative).
9. In Filters, set Min amount to `20`. Expect only Target. Type `abc` in the field and expect an inline error.
10. Change Target's category to Shopping. If a category filter is active, expect the row to stay visible and highlighted. Then open its **⋯** menu → **Make rule** → confirm. Expect a message saying the rule was created and how many transactions changed.

**Manual transactions**
11. **Add transaction**. Try to save with the fields empty, then with an amount of `0`. Expect an inline error each time. Add a valid one. First create a "Chase Checking" account (source "Manual entry") on the Accounts page, then add, for example, a $12.50 expense in the Restaurants category.
12. Its **⋯** menu has **Edit** and **Delete** (imported rows don't). Edit the amount, then delete it.

**Splitting a charge**
13. Open Target's **⋯** menu → **Split…**. Type `2` in "Split evenly among" and click **Fill in**. Expect My share to become 14.89 and "Paid for others: $14.88". Save.
14. Expect the row to show **$14.89** in bold with "of $29.77" underneath. On the Dashboard, expect total spending $50.82.
15. Open **Edit split…** and try a share of `50`. Expect an error saying it can't exceed the charge. Try `0`. Expect it to be accepted and the row to show "$0.00 of $29.77".
16. Choose **Remove split**. Expect the full $29.77 back.
17. Open the **⋯** menu on the Payment row. Expect no **Split…** item.

**Dashboard**
18. Check the numbers in [the sample data section](#4-the-sample-data).
19. Switch **By category** between Bars, Pie and Both, and reload the page. Expect your choice to be remembered. In Pie, the legend amounts and percentages should add up to the total.
20. Click the date buttons (This month, Last month, Last 6 months, Whole year, Last year). Expect the From and To fields to fill in and the button to stay highlighted. Typing your own dates should clear the highlight.
21. Add manual transactions in a second month. Expect a dashed **Median month** line on the Monthly trend chart once there are at least two months.
22. **Top merchants** controls: the **Top 5 / 10 / 25 / 50** picker sets how many rows show, and **Most spent** / **Most visits** changes the ranking. With the sample data there are only four merchants, so every count shows all four. Switch to **Most visits** and expect Blue Bottle (2 transactions) first, then Target, Netflix and Flik Cafe Az Qps. Add manual transactions at more merchants to see the count limit apply.
23. **Category** filter (in the Dashboard filters, next to Account): pick Restaurants. Expect every section to narrow to that category: total spending $20.44, the category chart showing only Restaurants at 100%, and Top merchants listing only Flik Cafe Az Qps and Blue Bottle. **Clear** resets it.

**Recurring**
24. Add three manual expenses at the same merchant, about a month apart, with similar amounts. Expect the merchant on the **Recurring** page as monthly, with the next expected date.

**Deleting an account**
25. **Accounts** → **Delete** on the Apple Card account. Expect a confirmation that names the number of transactions that will be removed. After confirming, expect the account, its transactions and its import history to be gone, and importing the sample again to work.

**Layout**
26. Narrow the browser window to a phone width (about 390 px). Expect the Transactions table to switch to stacked cards with the amount and ⋯ menu still visible. The top navigation bar is known to overflow at this width (see below).

## 7. Things worth trying to break

- Amounts with commas, dollar signs, three decimals, negatives, or very large values.
- Clicking buttons twice quickly (Import, Save split, Delete).
- Refreshing the page in the middle of an action.
- A CSV with a missing column, or with a bad date or amount. The importer should report the bad rows with line numbers and still import the good ones.
- Two overlapping exports: import `apple_sample.csv`, then a copy with extra rows added. Only the new rows should be added, and the two identical Blue Bottle rows should both survive.
- Very long merchant names, and names with special characters.

## Known limitations

These are already documented, so you don't need to report them:

- Renaming a category doesn't stop a later import (or re-applying rules) from re-creating the old name. See [Known limitations in the README](../README.md#known-limitations).
- The duplicate detection includes the clearing date, so a transaction whose clearing date changes between two exports can be imported twice.
- There is no undo for an import batch, and no screen for managing categories, rules or merchant aliases (those are available through the API).
- The top navigation bar overflows on phone-width screens.

## Reporting a bug

Please include:

1. **What you did**, as numbered steps, starting from an empty database.
2. **What you expected** and **what happened**.
3. **Where**: the page, plus the browser and operating system.
4. **Evidence**: a screenshot, and any red errors from the browser console (open developer tools) or the backend terminal.
5. **Whether it's reproducible** after a reset.

Use only the sample data in reports. Never paste real transactions, account names, or statements.
