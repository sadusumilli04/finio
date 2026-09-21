# Insights page — Design

Date: 2026-09-21

## Goal

A page that tells the user, month by month, what stands out in their spending: how the month compares with earlier ones, what changed, and what looks unusual. It answers "how did I do, what changed, what should I look at" without the user having to read charts.

## Decisions

- **Scope of v1** (chosen by the user): the month summary and pace, what changed (biggest movers, new merchants, merchants that grew), and unusual charges and subscription changes. Left for later: weekday/weekend patterns, the cardholder split, and "covered for others".
- **Architecture:** one backend endpoint, `GET /api/insights`, computes everything in a new service module and returns a structured result; the page only displays it. Each insight is its own small function so more can be added later. Rejected: assembling insights in the browser from existing endpoints (many requests, spending rules duplicated in TypeScript, and first-time merchants and outlier charges need raw transactions), and storing precomputed insights (over-built, can go stale).
- **Month selection:** a picker of the months that have spending. The page opens on the current month (in progress) or, if the current month has no spending yet, on the latest month with data.
- **No filters in v1** (no account or cardholder filter).
- Income and net cash flow are out of scope: Apple Card data has no income.

## Definitions

"Spending" is the same everywhere in the app: purchases only (`type = 'purchase'`), counted at the user's share (`EFFECTIVE_AMOUNT`, `backend/finio/services/amounts.py`), and purchases whose effective amount is 0 are left out. Amounts are integer cents. A month is a calendar month by `transaction_date`.

**Windows.** The selected month M is compared with the calendar month before it, P (which may have no spending). If M is the current calendar month (today's date, passed in so tests can pin it) it is **in progress**: the current window is days 1 to `days_elapsed`, and the previous window is days 1 to `min(days_elapsed, days_in_P)`, so a partial month is never compared with a full one. The response says which days were compared (`compared_with`, for example "Aug 1–20"). A complete month is compared over the whole of M against the whole of P. Months after the current month are rejected.

**Month at a glance (`summary`).**
- `total` for M's window, `previous_total` for P's window, `change` and `change_pct` (rounded to one decimal; `null` when the previous total is 0).
- `typical_total`: the median of the totals of all other **complete** months (excluding M and excluding the in-progress current month), only when there are at least 3; otherwise `null`.
- `rank`: M's position among all complete months, highest spending first, `{position, of}`, only when M is complete and there are at least 3 complete months; otherwise `null`.
- `projected_total`: only when in progress and `days_elapsed >= 7`: `round(total / days_elapsed * days_in_month)`; otherwise `null`.

**Biggest movers (`movers`).** For each category with spending in either window, `change = current - previous`. Changes smaller than $10 in absolute value are ignored. `up` lists the 3 largest increases, `down` the 3 largest decreases (largest first), each with the category, `current`, `previous`, `change` and `change_pct` (`null` when `previous` is 0, which the page labels "new").

**New merchants (`new_merchants`).** Merchants (non-empty `merchant_clean`) with spending in M's window and no counted spending (the definition above) dated before M's first day, largest total first (ties by name), at most 10. Empty when there is no earlier data at all (M is the earliest month), because everything would be "new".

**Merchants that grew (`growing_merchants`).** Merchants with spending in both windows whose `change >= $25` and `current >= 1.5 * previous`; at most 5, largest change first.

**Unusual charges (`unusual_charges`).** A purchase in M's window whose amount is at least 3 times the median effective amount of the purchases in its **category dated before M's first day**, and at least $50. The category needs at least 5 such earlier purchases. Each item carries the transaction id, date, merchant, category, `amount` and `typical` (the median). At most 5, largest amount first.

**Subscription changes (`subscriptions`).** Based on `find_recurring` run over all history, restricted to `cadence == "monthly"` (weekly, biweekly and yearly are too noisy for v1). Detection reflects today's data, so for a past month it shows what is recurring now. Per merchant, over its purchases, with kinds ordered `missing`, `price_up`, `price_down`, `new`:
- `price_up` / `price_down`: the merchant's latest charge in M's window versus its previous charge, when the difference is at least 5% of the previous charge and at least $1.
- `new`: the merchant's first charge is dated within the three calendar months ending with M.
- `missing`: no charge in M's window, and the expected date (the last charge before M's first day plus the merchant's median gap between charges) falls inside M's window and is at least 5 days before the end of the window (the last day of M, or today for an in-progress month).
Each item has the merchant, `kind`, `current` and `previous` amounts (where relevant) and `expected_date` (for `missing`).

All thresholds ($10, $25, 1.5x, 3x, $50, 5 earlier purchases, 5%, $1, 3 months, 5 days, day 7, 3 complete months) are named constants in one place.

## API

`GET /api/insights?month=YYYY-MM` (`month` optional). Amounts in cents.

```
{
  "month": "2026-09", "in_progress": true, "as_of": "2026-09-20",
  "days_elapsed": 20, "days_in_month": 30,
  "available_months": ["2026-01", ..., "2026-09"],
  "summary": { "total", "compared_with", "previous_total", "change", "change_pct",
               "typical_total", "rank", "projected_total" },
  "movers": { "up": [...], "down": [...] },
  "new_merchants": [...], "growing_merchants": [...],
  "unusual_charges": [...], "subscriptions": [...]
}
```

- List item fields (all amounts in cents):
  - `movers.up[]` / `movers.down[]`: `category`, `category_id`, `current`, `previous`, `change`, `change_pct` (`null` when `previous` is 0).
  - `new_merchants[]`: `merchant`, `total`, `count`.
  - `growing_merchants[]`: `merchant`, `current`, `previous`, `change`, `change_pct`.
  - `unusual_charges[]`: `transaction_id`, `date`, `merchant`, `category`, `amount`, `typical`.
  - `subscriptions[]`: `merchant`, `kind` (`missing`, `price_up`, `price_down` or `new`), `current`, `previous` (both `null` where not relevant, for example for `missing`), `expected_date` (only for `missing`).
- `available_months`: every month with spending, ascending. `days_elapsed` and `as_of` apply only to an in-progress month (otherwise `days_elapsed = days_in_month`).
- Default month when omitted: the current month if it has spending, else the latest available month; with no data at all, the current month with an empty result.
- A malformed month, or a month after the current one, returns 400 (`ValidationFailed`). A valid month with no spending returns an empty result, not an error.
- A `null` field means "not enough history yet"; lists are empty when nothing qualifies.
- The router stays thin; the logic lives in `backend/finio/services/insights.py` (one function per insight, each taking the date windows it needs), using `EFFECTIVE_AMOUNT` and `find_recurring`.

## UI

A new **Insights** item in the top navigation after Dashboard, at `/insights`.

- **Header:** the page title, a month dropdown (months with spending, newest first, the current one labelled "in progress") and previous/next arrows.
- **Month at a glance** (full width): the big total ("so far" while in progress), the change against last month in words ("Up $212.00 (+12%) vs Aug 1–20", colour-coded orange for up and green for down but always written out), the typical month, the rank ("3rd highest of 9 months"), and for an in-progress month "Day 20 of 30 · on pace for $1,851".
- **Cards** in a two-column grid (one column on a phone): Biggest movers (went up / went down), New merchants, Merchants that grew, Unusual charges (each showing "typical for <category>: $X"), Subscription changes (with a small tag: Price up, Price down, New, Missing). Each card has a one-line note on how it was computed and its own empty message ("No unusual charges this month"); where history is short it says what is missing ("Needs at least 3 other full months").
- **States:** an error alone, then "Loading…", then the content dimmed while refetching, like the Dashboard. With no data at all the page says "Import a statement to see insights".
- **Not in v1:** clicking a merchant to jump to its transactions, and account or cardholder filters.

## Edge cases

- Only one month of history: no previous month, so only the total is shown; movers and new merchants are empty; rank and typical are `null`.
- A previous month with no spending: changes are shown in dollars with no percent.
- Comparing in-progress March with February uses days 1 to 28 of each and says so.
- Splits, payments, refunds and $0 shares follow the Dashboard rules through `EFFECTIVE_AMOUNT`.
- Speed: totals are SQL aggregates; the outlier check runs in Python over the user's purchases, which is fine at personal-data scale.

## Testing

Backend (pytest), fabricated multi-month data with "today" pinned: each insight on its own, including both sides of every threshold, the same-days comparison (including February versus March and an in-progress month), first-month suppression, typical needing 3 complete months, rank, projection starting on day 7, the effect of a split and of a $0 share, subscription price changes, new and missing (with the grace period), and API tests for the bad-month 400, the future-month 400, the default month, the response shape, and an empty database.

Frontend (Vitest): the wording helpers ("Up $212.00 (+12%)", "Down ..."), month labels, the default-month rule, and previous/next month navigation. The page is checked in a browser against a throwaway database with fabricated months, at desktop and phone width.

## Delivery and docs

Built on `feat/insights-page` in the normal project folder (no worktrees). Docs to update: `docs/SPECIFICATION.md` (API and UI), `docs/REQUIREMENTS.md` (new requirements for the Insights page), the README, and `docs/TESTING.md` (walkthrough steps).
