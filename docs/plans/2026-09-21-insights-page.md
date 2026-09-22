# Insights Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Insights page that shows, for a chosen month, how spending compares with earlier months, what changed, and what looks unusual.

**Architecture:** One backend endpoint, `GET /api/insights?month=YYYY-MM`, assembled by `build_insights` from small pure-ish modules in a new package `backend/finio/services/insights/` (windows, spending totals, summary, changes, unusual charges, subscriptions). All spending numbers reuse the existing rule (purchases only, at the user's share, `<> 0`). The React page only displays the result.

**Tech Stack:** Python 3.13, FastAPI, stdlib `sqlite3`, pytest; React + TypeScript (Vite 6), Vitest.

**Spec:** `docs/specs/2026-09-21-insights-page-design.md`

## Global Constraints

- Work in the normal project folder on branch `feat/insights-page`. **Do not create or use git worktrees** (user's standing rule). Run git commands as plain, separate commands. Add files to git by path. Do not push, open PRs, or merge.
- Amounts are integer cents. "Spending" = `type = 'purchase'`, counted at the user's share (`EFFECTIVE_AMOUNT` from `backend/finio/services/amounts.py`), excluding purchases whose effective amount is 0 (`analytics.spending_where`, which uses `<> 0`). Never re-type the effective-amount expression; never aggregate raw `amount` for spending.
- Months are calendar months by `transaction_date`. The selected month M is compared with the previous calendar month P; an in-progress month (M = the current calendar month) is compared over the same days. "Today" is always a parameter (`date`), never read inside the calculation modules, so tests can pin it.
- All thresholds live in ONE module, `backend/finio/services/insights/constants.py`, as named constants.
- Domain errors come from `finio/errors.py` (`ValidationFailed` -> 400); no `HTTPException` in services. Routers stay thin.
- Queries alias the transactions table as `t` (`where_clause`/`spending_where` contract).
- Frontend: Node is 22.11, so Vite stays pinned to ^6 (do not upgrade vite, @vitejs/plugin-react or vitest); no new dependencies. Use `./node_modules/.bin/tsc -b`, not `npx tsc`.
- Never commit real financial data. Tests use fabricated rows only. Do not read the user's real database (`backend/data/`) or start anything on ports 5173/8000 (the user's running app); use ports 8001/5174 and a throwaway database (`FINIO_DB=<temp file>`) for any live check.
- Docs live in `docs/` (only README.md and CLAUDE.md are markdown at the repo root).
- Every commit message ends with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (pass as a second `-m`; do not substitute your own model name).
- Backend commands run from `backend/` with `.venv/bin/...`; frontend commands from `frontend/`.

---

## File Structure

```
backend/finio/
  deps.py                          # MODIFY: get_today()
  app.py                           # MODIFY: register the insights router
  api/insights.py                  # CREATE: GET /api/insights
  services/analytics.py            # MODIFY: rename _spending_where -> spending_where (public)
  services/insights/
    __init__.py                    # CREATE: build_insights(conn, month, today) -> dict
    constants.py                   # CREATE: every threshold
    windows.py                     # CREATE: Windows, build_windows, parse_month, month_key, shift_month
    common.py                      # CREATE: median_cents
    spending.py                    # CREATE: window_total, monthly_totals
    summary.py                     # CREATE: build_summary
    changes.py                     # CREATE: category_totals, merchant_totals, build_movers, build_growing, build_new_merchants
    unusual.py                     # CREATE: build_unusual
    subscriptions.py               # CREATE: build_subscriptions
backend/tests/
  test_insights_windows.py  test_insights_summary.py  test_insights_changes.py
  test_insights_unusual.py  test_insights_subscriptions.py  test_insights_api.py
frontend/src/
  api.ts                           # MODIFY: Insights types + api.insights(month?)
  lib/insights.ts (+ .test.ts)     # CREATE: monthLabel, neighborMonth, formatPercent, changeText, paceText, rankText, subscriptionTag
  components/InsightCard.tsx       # CREATE
  pages/Insights.tsx               # CREATE
  App.tsx                          # MODIFY: nav item + route
  styles.css                       # MODIFY: .insights-page styles
docs/                              # MODIFY: SPECIFICATION.md, REQUIREMENTS.md, TESTING.md; README.md at root
```

---

### Task 1: Constants and month windows

**Files:**
- Create: `backend/finio/services/insights/__init__.py` (empty for now), `constants.py`, `windows.py`, `backend/tests/test_insights_windows.py`

**Interfaces:**
- Produces:
  - `constants.py`: `MOVER_MIN_CHANGE=1000`, `MOVERS_PER_SIDE=3`, `NEW_MERCHANTS_LIMIT=10`, `GROWING_MIN_CHANGE=2500`, `GROWING_MIN_RATIO=1.5`, `GROWING_LIMIT=5`, `UNUSUAL_MIN_HISTORY=5`, `UNUSUAL_RATIO=3`, `UNUSUAL_MIN_AMOUNT=5000`, `UNUSUAL_LIMIT=5`, `SUBSCRIPTION_MIN_PCT=5`, `SUBSCRIPTION_MIN_CHANGE=100`, `SUBSCRIPTION_NEW_MONTHS=3`, `SUBSCRIPTION_MISSING_GRACE_DAYS=5`, `PROJECTION_MIN_DAYS=7`, `TYPICAL_MIN_MONTHS=3`.
  - `windows.py`: frozen dataclass `Windows(month: str, in_progress: bool, days_elapsed: int, days_in_month: int, month_start: date, current_start: date, current_end: date, previous_start: date, previous_end: date, compared_with: str, today_month: str)`; `parse_month(text: str) -> tuple[int, int]` (raises `ValidationFailed("month must look like 2026-09")`); `month_key(d: date) -> str` (`"2026-09"`); `shift_month(year: int, month: int, delta: int) -> tuple[int, int]`; `build_windows(month: str, today: date) -> Windows` (raises `ValidationFailed` for a malformed month or one after the current month).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_windows.py`:
```python
from datetime import date

import pytest

from finio.errors import ValidationFailed
from finio.services.insights.windows import build_windows, month_key, parse_month, shift_month


def test_in_progress_month_compares_the_same_days():
    w = build_windows("2026-09", date(2026, 9, 20))
    assert (w.in_progress, w.days_elapsed, w.days_in_month) == (True, 20, 30)
    assert (w.month_start, w.current_start, w.current_end) == (date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 20))
    assert (w.previous_start, w.previous_end) == (date(2026, 8, 1), date(2026, 8, 20))
    assert w.compared_with == "Aug 1–20"
    assert (w.month, w.today_month) == ("2026-09", "2026-09")


def test_complete_month_compares_whole_months():
    w = build_windows("2026-08", date(2026, 9, 20))
    assert (w.in_progress, w.days_elapsed, w.days_in_month) == (False, 31, 31)
    assert (w.current_start, w.current_end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert (w.previous_start, w.previous_end) == (date(2026, 7, 1), date(2026, 7, 31))
    assert w.compared_with == "Jul 1–31"
    assert w.today_month == "2026-09"


def test_previous_window_is_clamped_to_a_shorter_month():
    w = build_windows("2027-03", date(2027, 3, 31))
    assert (w.previous_start, w.previous_end) == (date(2027, 2, 1), date(2027, 2, 28))
    assert w.compared_with == "Feb 1–28"
    leap = build_windows("2028-03", date(2028, 3, 31))
    assert leap.previous_end == date(2028, 2, 29) and leap.compared_with == "Feb 1–29"


def test_january_compares_with_december_of_the_year_before():
    w = build_windows("2027-01", date(2027, 1, 15))
    assert (w.previous_start, w.previous_end) == (date(2026, 12, 1), date(2026, 12, 15))
    assert w.compared_with == "Dec 1–15"


def test_a_future_month_is_rejected():
    with pytest.raises(ValidationFailed):
        build_windows("2026-10", date(2026, 9, 20))
    with pytest.raises(ValidationFailed):
        build_windows("2027-01", date(2026, 9, 20))


@pytest.mark.parametrize("bad", ["", "abc", "2026-9", "26-09", "2026-13", "2026-00", "2026/09", "2026-09-01"])
def test_malformed_months_are_rejected(bad):
    with pytest.raises(ValidationFailed):
        parse_month(bad)


def test_helpers():
    assert parse_month("2026-09") == (2026, 9)
    assert month_key(date(2026, 9, 5)) == "2026-09"
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 9, -2) == (2026, 7)
    assert shift_month(2026, 12, 1) == (2027, 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_windows.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.insights`).

- [ ] **Step 3: Implement**

`backend/finio/services/insights/__init__.py`: empty file.

`backend/finio/services/insights/constants.py`:
```python
"""Every threshold the Insights page uses. Amounts are cents. Tune them here."""

MOVER_MIN_CHANGE = 1000            # ignore category changes under $10
MOVERS_PER_SIDE = 3

NEW_MERCHANTS_LIMIT = 10

GROWING_MIN_CHANGE = 2500          # a merchant grew by at least $25 ...
GROWING_MIN_RATIO = 1.5            # ... and to at least 1.5x last time
GROWING_LIMIT = 5

UNUSUAL_MIN_HISTORY = 5            # earlier purchases needed in the category
UNUSUAL_RATIO = 3                  # at least 3x the category's typical charge ...
UNUSUAL_MIN_AMOUNT = 5000          # ... and at least $50
UNUSUAL_LIMIT = 5

SUBSCRIPTION_MIN_PCT = 5           # a price change of at least 5% ...
SUBSCRIPTION_MIN_CHANGE = 100      # ... and at least $1
SUBSCRIPTION_NEW_MONTHS = 3        # "new" = first charge within the 3 months ending with the selected one
SUBSCRIPTION_MISSING_GRACE_DAYS = 5

PROJECTION_MIN_DAYS = 7            # project a month-end total from day 7 on
TYPICAL_MIN_MONTHS = 3             # other complete months needed for a "typical month" and a rank
```

`backend/finio/services/insights/windows.py`:
```python
import calendar
from dataclasses import dataclass
from datetime import date

from finio.errors import ValidationFailed


@dataclass(frozen=True)
class Windows:
    month: str
    in_progress: bool
    days_elapsed: int
    days_in_month: int
    month_start: date
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    compared_with: str
    today_month: str


def parse_month(text: str) -> tuple[int, int]:
    parts = text.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2 or not all(p.isdigit() for p in parts):
        raise ValidationFailed("month must look like 2026-09")
    year, month = int(parts[0]), int(parts[1])
    if not 1 <= month <= 12:
        raise ValidationFailed("month must look like 2026-09")
    return year, month


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def build_windows(month: str, today: date) -> Windows:
    year, mon = parse_month(month)
    if (year, mon) > (today.year, today.month):
        raise ValidationFailed("month cannot be after the current month")

    in_progress = (year, mon) == (today.year, today.month)
    days_in_month = calendar.monthrange(year, mon)[1]
    prev_year, prev_mon = shift_month(year, mon, -1)
    days_in_previous = calendar.monthrange(prev_year, prev_mon)[1]

    days_elapsed = today.day if in_progress else days_in_month
    previous_last_day = min(days_elapsed, days_in_previous) if in_progress else days_in_previous

    return Windows(
        month=f"{year:04d}-{mon:02d}",
        in_progress=in_progress,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        month_start=date(year, mon, 1),
        current_start=date(year, mon, 1),
        current_end=date(year, mon, days_elapsed),
        previous_start=date(prev_year, prev_mon, 1),
        previous_end=date(prev_year, prev_mon, previous_last_day),
        compared_with=f"{calendar.month_abbr[prev_mon]} 1–{previous_last_day}",
        today_month=month_key(today),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_insights_windows.py -q && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/insights backend/tests/test_insights_windows.py
git commit -m "feat: insights constants and month windows" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Spending totals and the month summary

**Files:**
- Modify: `backend/finio/services/analytics.py` (rename `_spending_where` -> `spending_where`)
- Create: `backend/finio/services/insights/common.py`, `spending.py`, `summary.py`, `backend/tests/test_insights_summary.py`

**Interfaces:**
- Consumes: `Windows`, constants (Task 1); `EFFECTIVE_AMOUNT`.
- Produces:
  - `analytics.spending_where(**filters) -> tuple[str, list]` (same behaviour as the old private helper; the 3 internal callers in analytics.py are updated).
  - `common.median_cents(values: list[int]) -> int | None` (`None` for an empty list; otherwise `int(round(statistics.median(values)))`).
  - `spending.window_total(conn, start: date, end: date) -> int` (sum of effective amounts of counted spending in the inclusive window; 0 when none); `spending.monthly_totals(conn) -> dict[str, int]` (`"YYYY-MM" -> total`, months with counted spending, in ascending order).
  - `summary.build_summary(windows: Windows, totals: dict[str, int], current_total: int, previous_total: int) -> dict` with keys `total`, `compared_with`, `previous_total`, `change`, `change_pct` (`None` when `previous_total == 0`, else rounded to 1 decimal), `typical_total` (median of the totals of all OTHER complete months, i.e. months `< windows.today_month` excluding `windows.month`, only if there are at least `TYPICAL_MIN_MONTHS`, else `None`), `rank` (`{"position", "of"}` when the month is complete, has spending, and there are at least `TYPICAL_MIN_MONTHS` complete months; `position = 1 + number of complete months with a strictly higher total`; else `None`), `projected_total` (in progress and `days_elapsed >= PROJECTION_MIN_DAYS`: `round(current_total / days_elapsed * days_in_month)`, else `None`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_summary.py`:
```python
from datetime import date

from finio.services.insights.common import median_cents
from finio.services.insights.spending import monthly_totals, window_total
from finio.services.insights.summary import build_summary
from finio.services.insights.windows import build_windows
from tests.helpers import insert_txn

TOTALS = {"2026-01": 100000, "2026-02": 120000, "2026-03": 90000, "2026-04": 150000, "2026-05": 110000}
JUNE_15 = date(2026, 6, 15)


def test_median_cents():
    assert median_cents([]) is None
    assert median_cents([300, 100, 200]) == 200
    assert median_cents([100, 200, 300, 400]) == 250


def test_change_and_percent_for_a_complete_month():
    w = build_windows("2026-05", JUNE_15)
    s = build_summary(w, TOTALS, 110000, 150000)
    assert (s["total"], s["previous_total"], s["change"], s["change_pct"]) == (110000, 150000, -40000, -26.7)
    assert s["compared_with"] == "Apr 1–30"


def test_percent_is_none_when_the_previous_total_is_zero():
    w = build_windows("2026-05", JUNE_15)
    s = build_summary(w, TOTALS, 110000, 0)
    assert (s["change"], s["change_pct"]) == (110000, None)


def test_typical_month_is_the_median_of_the_other_complete_months():
    w = build_windows("2026-05", JUNE_15)
    assert build_summary(w, TOTALS, 110000, 150000)["typical_total"] == 110000   # median of Jan-Apr


def test_typical_needs_three_other_complete_months():
    w = build_windows("2026-05", JUNE_15)
    assert build_summary(w, {"2026-04": 1, "2026-05": 2}, 2, 1)["typical_total"] is None
    three = {"2026-02": 100, "2026-03": 300, "2026-04": 200, "2026-05": 999}
    assert build_summary(w, three, 999, 200)["typical_total"] == 200


def test_the_month_in_progress_is_not_part_of_the_typical_month():
    w = build_windows("2026-06", JUNE_15)
    totals = {**TOTALS, "2026-06": 5000}
    s = build_summary(w, totals, 5000, 110000)
    assert s["typical_total"] == 110000            # Jan-May only, the partial June is excluded
    assert s["rank"] is None                       # no rank for a month in progress


def test_rank_among_complete_months():
    w_high = build_windows("2026-04", JUNE_15)
    assert build_summary(w_high, TOTALS, 150000, 90000)["rank"] == {"position": 1, "of": 5}
    w_low = build_windows("2026-03", JUNE_15)
    assert build_summary(w_low, TOTALS, 90000, 120000)["rank"] == {"position": 5, "of": 5}


def test_rank_needs_three_complete_months():
    w = build_windows("2026-05", JUNE_15)
    assert build_summary(w, {"2026-04": 1, "2026-05": 2}, 2, 1)["rank"] is None


def test_projection_starts_on_day_seven():
    day20 = build_windows("2026-09", date(2026, 9, 20))
    assert build_summary(day20, {}, 100000, 80000)["projected_total"] == 150000   # 100000 / 20 * 30
    day7 = build_windows("2026-09", date(2026, 9, 7))
    assert build_summary(day7, {}, 21000, 0)["projected_total"] == 90000           # 21000 / 7 * 30
    day6 = build_windows("2026-09", date(2026, 9, 6))
    assert build_summary(day6, {}, 21000, 0)["projected_total"] is None
    complete = build_windows("2026-08", date(2026, 9, 20))
    assert build_summary(complete, {}, 21000, 0)["projected_total"] is None


def test_window_total_and_monthly_totals(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-09-01", amount=1000)
    insert_txn(conn, acct, date="2026-09-20", amount=2000)
    insert_txn(conn, acct, date="2026-09-21", amount=4000)                      # outside the window
    insert_txn(conn, acct, date="2026-09-10", amount=-5000, type="payment")     # not spending
    insert_txn(conn, acct, date="2026-09-11", amount=9000, my_share=0)          # fully repaid: left out
    insert_txn(conn, acct, date="2026-09-12", amount=6000, my_share=1500)       # counted at the share
    insert_txn(conn, acct, date="2026-08-05", amount=700)
    assert window_total(conn, date(2026, 9, 1), date(2026, 9, 20)) == 4500       # 1000 + 2000 + 1500
    assert window_total(conn, date(2026, 7, 1), date(2026, 7, 31)) == 0
    assert monthly_totals(conn) == {"2026-08": 700, "2026-09": 8500}             # 1000 + 2000 + 4000 + 1500
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_summary.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.insights.common`).

- [ ] **Step 3: Rename the analytics helper**

In `backend/finio/services/analytics.py` rename `_spending_where` to `spending_where` (the definition on line 7 and its 3 calls). No behaviour change. Run `cd backend && .venv/bin/pytest -q` (all earlier tests still pass).

- [ ] **Step 4: Implement**

`backend/finio/services/insights/common.py`:
```python
import statistics


def median_cents(values: list[int]) -> int | None:
    """Median of amounts in cents, rounded to a whole cent; None for an empty list."""
    if not values:
        return None
    return int(round(statistics.median(values)))
```

`backend/finio/services/insights/spending.py`:
```python
import sqlite3
from datetime import date

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where


def window_total(conn: sqlite3.Connection, start: date, end: date) -> int:
    """What the user spent between two dates (inclusive), at their share."""
    where, params = spending_where(date_from=start, date_to=end)
    row = conn.execute(f"SELECT COALESCE(SUM({EFFECTIVE_AMOUNT}), 0) FROM transactions t WHERE {where}", params)
    return row.fetchone()[0]


def monthly_totals(conn: sqlite3.Connection) -> dict[str, int]:
    """Total spending per calendar month ("YYYY-MM"), months with spending only, oldest first."""
    where, params = spending_where()
    rows = conn.execute(
        f"SELECT strftime('%Y-%m', t.transaction_date) AS month, SUM({EFFECTIVE_AMOUNT}) AS total "
        f"FROM transactions t WHERE {where} GROUP BY month ORDER BY month",
        params,
    )
    return {r["month"]: r["total"] for r in rows}
```

`backend/finio/services/insights/summary.py`:
```python
from finio.services.insights.common import median_cents
from finio.services.insights.constants import PROJECTION_MIN_DAYS, TYPICAL_MIN_MONTHS
from finio.services.insights.windows import Windows


def build_summary(windows: Windows, totals: dict[str, int], current_total: int, previous_total: int) -> dict:
    change = current_total - previous_total
    change_pct = None if previous_total == 0 else round(change / previous_total * 100, 1)

    complete = {month: total for month, total in totals.items() if month < windows.today_month}
    others = [total for month, total in complete.items() if month != windows.month]
    typical = median_cents(others) if len(others) >= TYPICAL_MIN_MONTHS else None

    rank = None
    if not windows.in_progress and windows.month in complete and len(complete) >= TYPICAL_MIN_MONTHS:
        position = 1 + sum(1 for total in complete.values() if total > complete[windows.month])
        rank = {"position": position, "of": len(complete)}

    projected = None
    if windows.in_progress and windows.days_elapsed >= PROJECTION_MIN_DAYS:
        projected = round(current_total / windows.days_elapsed * windows.days_in_month)

    return {
        "total": current_total,
        "compared_with": windows.compared_with,
        "previous_total": previous_total,
        "change": change,
        "change_pct": change_pct,
        "typical_total": typical,
        "rank": rank,
        "projected_total": projected,
    }
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finio/services/analytics.py backend/finio/services/insights backend/tests/test_insights_summary.py
git commit -m "feat: insights spending totals and month summary" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: What changed — movers, new merchants, merchants that grew

**Files:**
- Create: `backend/finio/services/insights/changes.py`, `backend/tests/test_insights_changes.py`

**Interfaces:**
- Consumes: `Windows`, constants, `spending_where`, `EFFECTIVE_AMOUNT`.
- Produces:
  - `category_totals(conn, start: date, end: date) -> dict[int, dict]` — `{category_id: {"category": str, "total": int}}` for counted spending in the window.
  - `merchant_totals(conn, start: date, end: date) -> dict[str, dict]` — `{merchant: {"total": int, "count": int}}` (non-empty `merchant_clean` only).
  - `build_movers(current: dict[int, dict], previous: dict[int, dict]) -> {"up": [...], "down": [...]}` — items `{"category", "category_id", "current", "previous", "change", "change_pct"}`; ignores `abs(change) < MOVER_MIN_CHANGE`; `up` = largest increases first (ties by name), `down` = largest decreases first, each at most `MOVERS_PER_SIDE`; `change_pct` is `None` when `previous` is 0, else rounded to 1 decimal.
  - `build_growing(current: dict[str, dict], previous: dict[str, dict]) -> list[dict]` — items `{"merchant", "current", "previous", "change", "change_pct"}` for merchants in both with `previous > 0`, `change >= GROWING_MIN_CHANGE` and `current >= GROWING_MIN_RATIO * previous`; largest change first (ties by name), at most `GROWING_LIMIT`.
  - `build_new_merchants(conn, windows: Windows) -> list[dict]` — items `{"merchant", "total", "count"}`: merchants with counted spending in the current window and none dated before `windows.month_start`; `[]` when there is no counted spending before the month at all; largest total first (ties by name), at most `NEW_MERCHANTS_LIMIT`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_changes.py`:
```python
from datetime import date

from finio.services.insights.changes import (
    build_growing,
    build_movers,
    build_new_merchants,
    category_totals,
    merchant_totals,
)
from finio.services.insights.windows import build_windows
from tests.helpers import insert_txn


def cats(**totals):
    return {i: {"category": name, "total": total} for i, (name, total) in enumerate(totals.items(), start=1)}


def test_movers_split_into_up_and_down_and_ignore_small_changes():
    current = {1: {"category": "Grocery", "total": 30000}, 2: {"category": "Dining", "total": 5000},
               3: {"category": "Travel", "total": 20000}, 5: {"category": "Tiny", "total": 500}}
    previous = {1: {"category": "Grocery", "total": 20000}, 2: {"category": "Dining", "total": 25000},
                4: {"category": "Gym", "total": 5000}}
    movers = build_movers(current, previous)
    assert [(m["category"], m["change"], m["change_pct"]) for m in movers["up"]] == [
        ("Travel", 20000, None),      # new: nothing before, so no percent
        ("Grocery", 10000, 50.0),
    ]
    assert [(m["category"], m["change"], m["change_pct"]) for m in movers["down"]] == [
        ("Dining", -20000, -80.0),
        ("Gym", -5000, -100.0),
    ]
    assert movers["up"][0] == {"category": "Travel", "category_id": 3, "current": 20000, "previous": 0,
                               "change": 20000, "change_pct": None}


def test_movers_threshold_boundary_and_limit():
    at_threshold = build_movers({1: {"category": "A", "total": 1000}}, {})
    assert [m["category"] for m in at_threshold["up"]] == ["A"]                 # exactly $10 counts
    below = build_movers({1: {"category": "A", "total": 999}}, {})
    assert below == {"up": [], "down": []}
    many = {i: {"category": f"C{i}", "total": i * 2000} for i in range(1, 7)}
    assert [m["category"] for m in build_movers(many, {})["up"]] == ["C6", "C5", "C4"]   # at most 3


def test_growing_merchants():
    current = {"Alpha": {"total": 9000, "count": 3}, "Bravo": {"total": 3000, "count": 1},
               "Charlie": {"total": 5000, "count": 1}, "Echo": {"total": 7500, "count": 2},
               "Foxtrot": {"total": 7499, "count": 2}, "Golf": {"total": 9000, "count": 1}}
    previous = {"Alpha": {"total": 4000, "count": 1}, "Bravo": {"total": 2500, "count": 1},
                "Charlie": {"total": 4000, "count": 1}, "Delta": {"total": 9000, "count": 1},
                "Echo": {"total": 5000, "count": 1}, "Foxtrot": {"total": 5000, "count": 1}}
    grown = build_growing(current, previous)
    # Alpha +5000 (2.25x) qualifies; Echo is exactly +2500 and exactly 1.5x, which counts;
    # Foxtrot is +2499 (just under); Bravo and Charlie grew too little; Delta is gone; Golf has no history.
    assert [(g["merchant"], g["change"], g["change_pct"]) for g in grown] == [("Alpha", 5000, 125.0), ("Echo", 2500, 50.0)]
    assert grown[0] == {"merchant": "Alpha", "current": 9000, "previous": 4000, "change": 5000, "change_pct": 125.0}


def test_category_and_merchant_totals_use_the_users_share(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-09-05", amount=6000, my_share=1500, merchant="Home Plate", category="Restaurants")
    insert_txn(conn, acct, date="2026-09-06", amount=1000, merchant="Home Plate", category="Restaurants")
    insert_txn(conn, acct, date="2026-09-07", amount=800, merchant="Target", category="Grocery")
    insert_txn(conn, acct, date="2026-10-01", amount=5000, merchant="Later", category="Grocery")   # outside
    start, end = date(2026, 9, 1), date(2026, 9, 30)
    by_cat = {v["category"]: v["total"] for v in category_totals(conn, start, end).values()}
    assert by_cat == {"Restaurants": 2500, "Grocery": 800}
    assert merchant_totals(conn, start, end) == {"Home Plate": {"total": 2500, "count": 2},
                                                  "Target": {"total": 800, "count": 1}}


def test_new_merchants_are_first_time_places_this_month(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-10", amount=1000, merchant="Alpha")
    insert_txn(conn, acct, date="2026-09-02", amount=500, merchant="Alpha")
    insert_txn(conn, acct, date="2026-09-03", amount=3000, merchant="Bravo")
    insert_txn(conn, acct, date="2026-09-04", amount=2000, merchant="Charlie")
    insert_txn(conn, acct, date="2026-09-05", amount=2000, merchant="Charlie")
    w = build_windows("2026-09", date(2026, 9, 20))
    assert build_new_merchants(conn, w) == [
        {"merchant": "Charlie", "total": 4000, "count": 2},
        {"merchant": "Bravo", "total": 3000, "count": 1},
    ]


def test_new_merchants_are_empty_for_the_first_month_of_data(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-09-03", amount=3000, merchant="Bravo")
    assert build_new_merchants(conn, build_windows("2026-09", date(2026, 9, 20))) == []


def test_new_merchants_limit_and_ordering(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-10", amount=1000, merchant="Old")
    for i in range(12):
        insert_txn(conn, acct, date="2026-09-03", amount=1000 + i, merchant=f"M{i:02d}")
    found = build_new_merchants(conn, build_windows("2026-09", date(2026, 9, 20)))
    assert len(found) == 10 and found[0]["merchant"] == "M11"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_changes.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.insights.changes`).

- [ ] **Step 3: Implement**

`backend/finio/services/insights/changes.py`:
```python
import sqlite3
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.constants import (
    GROWING_LIMIT,
    GROWING_MIN_CHANGE,
    GROWING_MIN_RATIO,
    MOVER_MIN_CHANGE,
    MOVERS_PER_SIDE,
    NEW_MERCHANTS_LIMIT,
)
from finio.services.insights.windows import Windows


def category_totals(conn: sqlite3.Connection, start: date, end: date) -> dict[int, dict]:
    where, params = spending_where(date_from=start, date_to=end)
    rows = conn.execute(
        f"SELECT c.id AS category_id, c.name AS category, SUM({EFFECTIVE_AMOUNT}) AS total "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id WHERE {where} GROUP BY c.id",
        params,
    )
    return {r["category_id"]: {"category": r["category"], "total": r["total"]} for r in rows}


def merchant_totals(conn: sqlite3.Connection, start: date, end: date) -> dict[str, dict]:
    where, params = spending_where(date_from=start, date_to=end)
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, SUM({EFFECTIVE_AMOUNT}) AS total, COUNT(*) AS count "
        f"FROM transactions t WHERE {where} AND t.merchant_clean != '' GROUP BY t.merchant_clean",
        params,
    )
    return {r["merchant"]: {"total": r["total"], "count": r["count"]} for r in rows}


def _percent(change: int, previous: int) -> float | None:
    return None if previous == 0 else round(change / previous * 100, 1)


def build_movers(current: dict[int, dict], previous: dict[int, dict]) -> dict:
    items = []
    for category_id in current.keys() | previous.keys():
        now, before = current.get(category_id), previous.get(category_id)
        name = (now or before)["category"]
        current_total = now["total"] if now else 0
        previous_total = before["total"] if before else 0
        change = current_total - previous_total
        if abs(change) < MOVER_MIN_CHANGE:
            continue
        items.append({
            "category": name, "category_id": category_id, "current": current_total,
            "previous": previous_total, "change": change, "change_pct": _percent(change, previous_total),
        })
    up = sorted((i for i in items if i["change"] > 0), key=lambda i: (-i["change"], i["category"]))
    down = sorted((i for i in items if i["change"] < 0), key=lambda i: (i["change"], i["category"]))
    return {"up": up[:MOVERS_PER_SIDE], "down": down[:MOVERS_PER_SIDE]}


def build_growing(current: dict[str, dict], previous: dict[str, dict]) -> list[dict]:
    items = []
    for merchant, now in current.items():
        before = previous.get(merchant)
        if not before or before["total"] <= 0:
            continue
        change = now["total"] - before["total"]
        if change >= GROWING_MIN_CHANGE and now["total"] >= GROWING_MIN_RATIO * before["total"]:
            items.append({
                "merchant": merchant, "current": now["total"], "previous": before["total"],
                "change": change, "change_pct": _percent(change, before["total"]),
            })
    items.sort(key=lambda i: (-i["change"], i["merchant"]))
    return items[:GROWING_LIMIT]


def build_new_merchants(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    where, params = spending_where(date_to=windows.month_start - timedelta(days=1))
    if conn.execute(f"SELECT 1 FROM transactions t WHERE {where} LIMIT 1", params).fetchone() is None:
        return []   # no earlier data at all: everything would look new
    earlier = {
        r["merchant"]
        for r in conn.execute(f"SELECT DISTINCT t.merchant_clean AS merchant FROM transactions t WHERE {where}", params)
    }
    current = merchant_totals(conn, windows.current_start, windows.current_end)
    items = [
        {"merchant": merchant, "total": data["total"], "count": data["count"]}
        for merchant, data in current.items()
        if merchant not in earlier
    ]
    items.sort(key=lambda i: (-i["total"], i["merchant"]))
    return items[:NEW_MERCHANTS_LIMIT]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/insights/changes.py backend/tests/test_insights_changes.py
git commit -m "feat: insights movers, new merchants and growing merchants" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Unusual charges

**Files:**
- Create: `backend/finio/services/insights/unusual.py`, `backend/tests/test_insights_unusual.py`

**Interfaces:**
- Consumes: `Windows`, constants, `median_cents`, `spending_where`, `EFFECTIVE_AMOUNT`.
- Produces: `build_unusual(conn, windows: Windows) -> list[dict]` — items `{"transaction_id": int, "date": "YYYY-MM-DD", "merchant": str, "category": str, "amount": int, "typical": int}`. A purchase in the current window (effective amount `> 0`) is included when its category has at least `UNUSUAL_MIN_HISTORY` earlier purchases (dated before `windows.month_start`, effective amount `> 0`), and `amount >= UNUSUAL_RATIO * typical` (typical = `median_cents` of those earlier amounts) and `amount >= UNUSUAL_MIN_AMOUNT`. Largest amount first (ties by date, then id), at most `UNUSUAL_LIMIT`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_unusual.py`:
```python
from datetime import date

from finio.services.insights.unusual import build_unusual
from finio.services.insights.windows import build_windows
from tests.helpers import insert_txn

SEP = build_windows("2026-09", date(2026, 9, 20))


def seed_history(conn, acct, category="Shopping", n=5, amount=5000):
    for i in range(n):
        insert_txn(conn, acct, date="2026-08-10", amount=amount, category=category, merchant=f"Hist{i}")


def test_a_charge_three_times_the_typical_amount_is_flagged(conn, make_account):
    acct = make_account()
    seed_history(conn, acct)                                   # typical charge in Shopping: $50
    big = insert_txn(conn, acct, date="2026-09-12", amount=15000, category="Shopping", merchant="Best Buy")
    insert_txn(conn, acct, date="2026-09-13", amount=14999, category="Shopping", merchant="Just Under")
    assert build_unusual(conn, SEP) == [{
        "transaction_id": big, "date": "2026-09-12", "merchant": "Best Buy",
        "category": "Shopping", "amount": 15000, "typical": 5000,
    }]


def test_a_category_needs_five_earlier_purchases(conn, make_account):
    acct = make_account()
    seed_history(conn, acct, n=4)
    insert_txn(conn, acct, date="2026-09-12", amount=90000, category="Shopping")
    assert build_unusual(conn, SEP) == []


def test_the_charge_must_also_be_at_least_fifty_dollars(conn, make_account):
    acct = make_account()
    seed_history(conn, acct, amount=1000)                      # typical $10
    insert_txn(conn, acct, date="2026-09-12", amount=4000, category="Shopping", merchant="Four X")   # 4x but under $50
    fifty = insert_txn(conn, acct, date="2026-09-13", amount=5000, category="Shopping", merchant="Five X")
    assert [u["transaction_id"] for u in build_unusual(conn, SEP)] == [fifty]


def test_only_the_users_share_counts(conn, make_account):
    acct = make_account()
    seed_history(conn, acct)
    covered = insert_txn(conn, acct, date="2026-09-12", amount=60000, my_share=15000, category="Shopping", merchant="Split A")
    insert_txn(conn, acct, date="2026-09-13", amount=60000, my_share=10000, category="Shopping", merchant="Split B")
    found = build_unusual(conn, SEP)
    assert [(u["transaction_id"], u["amount"]) for u in found] == [(covered, 15000)]   # $150 = 3x; $100 is only 2x


def test_history_is_before_the_month_and_other_categories_do_not_count(conn, make_account):
    acct = make_account()
    seed_history(conn, acct, category="Grocery")               # history in a different category
    insert_txn(conn, acct, date="2026-09-12", amount=90000, category="Shopping", merchant="Shop")
    assert build_unusual(conn, SEP) == []
    seed_history(conn, acct, category="Shopping")
    insert_txn(conn, acct, date="2026-09-05", amount=40000, category="Shopping", merchant="Early Sep")   # this month, not history
    assert [u["merchant"] for u in build_unusual(conn, SEP)] == ["Shop", "Early Sep"]


def test_only_purchases_inside_the_window_are_candidates(conn, make_account):
    acct = make_account()
    seed_history(conn, acct)
    insert_txn(conn, acct, date="2026-09-25", amount=90000, category="Shopping", merchant="Future")   # after "today"
    insert_txn(conn, acct, date="2026-08-20", amount=90000, category="Shopping", merchant="Last month")
    assert build_unusual(conn, SEP) == []


def test_negative_purchase_rows_are_not_history(conn, make_account):
    acct = make_account()
    seed_history(conn, acct)
    for i in range(3):
        insert_txn(conn, acct, date="2026-08-11", amount=-3000, category="Shopping", merchant=f"Refund{i}")
    insert_txn(conn, acct, date="2026-09-12", amount=15000, category="Shopping", merchant="Best Buy")
    found = build_unusual(conn, SEP)
    assert [(u["merchant"], u["typical"]) for u in found] == [("Best Buy", 5000)]


def test_largest_first_and_at_most_five(conn, make_account):
    acct = make_account()
    seed_history(conn, acct)
    for i in range(7):
        insert_txn(conn, acct, date="2026-09-10", amount=20000 + i * 1000, category="Shopping", merchant=f"Big{i}")
    found = build_unusual(conn, SEP)
    assert [u["merchant"] for u in found] == ["Big6", "Big5", "Big4", "Big3", "Big2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_unusual.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.insights.unusual`).

- [ ] **Step 3: Implement**

`backend/finio/services/insights/unusual.py`:
```python
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.common import median_cents
from finio.services.insights.constants import (
    UNUSUAL_LIMIT,
    UNUSUAL_MIN_AMOUNT,
    UNUSUAL_MIN_HISTORY,
    UNUSUAL_RATIO,
)
from finio.services.insights.windows import Windows


def _category_history(conn: sqlite3.Connection, before: date) -> dict[int, list[int]]:
    where, params = spending_where(date_to=before - timedelta(days=1))
    history: dict[int, list[int]] = defaultdict(list)
    rows = conn.execute(
        f"SELECT t.category_id AS category_id, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE {where} AND {EFFECTIVE_AMOUNT} > 0",
        params,
    )
    for r in rows:
        history[r["category_id"]].append(r["amount"])
    return history


def build_unusual(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    history = _category_history(conn, windows.month_start)
    where, params = spending_where(date_from=windows.current_start, date_to=windows.current_end)
    rows = conn.execute(
        f"SELECT t.id AS transaction_id, t.transaction_date AS date, t.merchant_clean AS merchant, "
        f"t.category_id AS category_id, c.name AS category, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t JOIN categories c ON c.id = t.category_id "
        f"WHERE {where} AND {EFFECTIVE_AMOUNT} > 0",
        params,
    )
    items = []
    for r in rows:
        earlier = history.get(r["category_id"], [])
        if len(earlier) < UNUSUAL_MIN_HISTORY:
            continue
        typical = median_cents(earlier)
        if r["amount"] >= UNUSUAL_RATIO * typical and r["amount"] >= UNUSUAL_MIN_AMOUNT:
            items.append({
                "transaction_id": r["transaction_id"], "date": r["date"], "merchant": r["merchant"],
                "category": r["category"], "amount": r["amount"], "typical": typical,
            })
    items.sort(key=lambda i: (-i["amount"], i["date"], i["transaction_id"]))
    return items[:UNUSUAL_LIMIT]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/insights/unusual.py backend/tests/test_insights_unusual.py
git commit -m "feat: insights unusual charges" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Subscription changes

**Files:**
- Create: `backend/finio/services/insights/subscriptions.py`, `backend/tests/test_insights_subscriptions.py`

**Interfaces:**
- Consumes: `Windows`, `shift_month`, constants, `spending_where`, `EFFECTIVE_AMOUNT`, `find_recurring` (existing, `backend/finio/services/recurring.py`; returns dicts with `merchant` and `cadence`).
- Produces: `build_subscriptions(conn, windows: Windows) -> list[dict]` — items `{"merchant": str, "kind": "missing"|"price_up"|"price_down"|"new", "current": int | None, "previous": int | None, "expected_date": str | None}`, ordered by kind (`missing`, `price_up`, `price_down`, `new`) then merchant. Only merchants that `find_recurring(conn)` reports with `cadence == "monthly"` are considered, using each merchant's counted purchases with effective amount `> 0`, oldest first:
  - `price_up`/`price_down`: the latest charge inside the current window differs from the charge just before it by at least `max(SUBSCRIPTION_MIN_CHANGE, previous * SUBSCRIPTION_MIN_PCT / 100)` (`current` = the latest charge, `previous` = the one before it).
  - `missing`: no charge inside the window, at least 2 charges dated before `windows.month_start`, and `expected = last charge before the month + round(median gap in days between the charges before the month)` lies within `[windows.current_start, windows.current_end - SUBSCRIPTION_MISSING_GRACE_DAYS days]` (`current = None`, `previous` = that last charge, `expected_date` = ISO date).
  - `new`: the merchant's first-ever charge is dated within `[first day of (month - (SUBSCRIPTION_NEW_MONTHS - 1)), windows.current_end]` (`current` = the latest charge inside the window or `None`, `previous = None`).
  A merchant can appear more than once with different kinds; `expected_date` is `None` except for `missing`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_subscriptions.py`:
```python
from datetime import date

from finio.services.insights.subscriptions import build_subscriptions
from finio.services.insights.windows import build_windows
from tests.helpers import insert_txn

AUG = build_windows("2026-08", date(2026, 9, 20))     # a complete month


def series(conn, acct, merchant, dates, amounts):
    for d, a in zip(dates, amounts):
        insert_txn(conn, acct, date=d, amount=a, merchant=merchant, category="Entertainment")


def monthly(day, months):
    return [f"2026-{m:02d}-{day:02d}" for m in months]


def kinds(items):
    return [(i["kind"], i["merchant"]) for i in items]


def test_all_four_kinds_in_a_complete_month(conn, make_account):
    acct = make_account()
    series(conn, acct, "Spotify", monthly(10, range(3, 9)), [1000] * 5 + [1200])     # price went up
    series(conn, acct, "Dropbox", monthly(10, range(3, 9)), [1200] * 5 + [1000])     # price went down
    series(conn, acct, "Hulu", monthly(20, [6, 7, 8]), [1500] * 3)                   # started in June
    series(conn, acct, "Gym", monthly(5, [5, 6, 7]), [1000] * 3)                     # no August charge
    series(conn, acct, "Netflix", monthly(15, range(3, 9)), [1000] * 6)              # steady, nothing to report
    assert kinds(build_subscriptions(conn, AUG)) == [
        ("missing", "Gym"), ("price_up", "Spotify"), ("price_down", "Dropbox"), ("new", "Hulu"),
    ]


def test_item_fields(conn, make_account):
    acct = make_account()
    series(conn, acct, "Spotify", monthly(10, range(3, 9)), [1000] * 5 + [1200])
    series(conn, acct, "Gym", monthly(5, [5, 6, 7]), [1000] * 3)
    series(conn, acct, "Hulu", monthly(20, [6, 7, 8]), [1500] * 3)
    by_kind = {i["kind"]: i for i in build_subscriptions(conn, AUG)}
    assert by_kind["price_up"] == {"merchant": "Spotify", "kind": "price_up", "current": 1200, "previous": 1000, "expected_date": None}
    assert by_kind["missing"] == {"merchant": "Gym", "kind": "missing", "current": None, "previous": 1000, "expected_date": "2026-08-04"}
    assert by_kind["new"] == {"merchant": "Hulu", "kind": "new", "current": 1500, "previous": None, "expected_date": None}


def test_price_change_needs_five_percent_and_a_dollar(conn, make_account):
    acct = make_account()
    series(conn, acct, "Small", monthly(10, range(3, 9)), [1000] * 5 + [1050])       # +5% but only $0.50
    series(conn, acct, "Big", monthly(11, range(3, 9)), [1000] * 5 + [1100])         # +10% and $1.00
    assert kinds(build_subscriptions(conn, AUG)) == [("price_up", "Big")]


def test_only_monthly_charges_are_considered(conn, make_account):
    acct = make_account()
    series(conn, acct, "Coffee Club", ["2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24"], [500] * 4)   # weekly
    assert build_subscriptions(conn, AUG) == []


def test_missing_charge_in_a_month_in_progress_waits_for_the_grace_period(conn, make_account):
    acct = make_account()
    series(conn, acct, "Gym", ["2026-06-03", "2026-07-03", "2026-08-03"], [1000] * 3)   # next one expected about Sep 2
    late = build_windows("2026-09", date(2026, 9, 20))
    assert kinds(build_subscriptions(conn, late)) == [("missing", "Gym")]
    assert build_subscriptions(conn, late)[0]["expected_date"] == "2026-09-02"
    early = build_windows("2026-09", date(2026, 9, 5))          # only 3 days past the expected date
    assert build_subscriptions(conn, early) == []


def test_a_month_without_earlier_history_has_no_missing_items(conn, make_account):
    acct = make_account()
    series(conn, acct, "Gym", ["2026-06-03", "2026-07-03", "2026-08-03"], [1000] * 3)
    june = build_windows("2026-06", date(2026, 9, 20))          # the merchant's first month: nothing before it
    assert [i for i in build_subscriptions(conn, june) if i["kind"] == "missing"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_subscriptions.py -q`
Expected: FAIL (`ModuleNotFoundError: finio.services.insights.subscriptions`).

- [ ] **Step 3: Implement**

`backend/finio/services/insights/subscriptions.py`:
```python
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta

from finio.services.amounts import EFFECTIVE_AMOUNT
from finio.services.analytics import spending_where
from finio.services.insights.constants import (
    SUBSCRIPTION_MIN_CHANGE,
    SUBSCRIPTION_MIN_PCT,
    SUBSCRIPTION_MISSING_GRACE_DAYS,
    SUBSCRIPTION_NEW_MONTHS,
)
from finio.services.insights.windows import Windows, shift_month
from finio.services.recurring import find_recurring

KIND_ORDER = {"missing": 0, "price_up": 1, "price_down": 2, "new": 3}


def _item(merchant: str, kind: str, current: int | None, previous: int | None, expected: date | None = None) -> dict:
    return {
        "merchant": merchant, "kind": kind, "current": current, "previous": previous,
        "expected_date": expected.isoformat() if expected else None,
    }


def _charges(conn: sqlite3.Connection, merchants: set[str]) -> dict[str, list[tuple[date, int]]]:
    where, params = spending_where()
    rows = conn.execute(
        f"SELECT t.merchant_clean AS merchant, t.transaction_date AS d, {EFFECTIVE_AMOUNT} AS amount "
        f"FROM transactions t WHERE {where} AND {EFFECTIVE_AMOUNT} > 0 ORDER BY t.transaction_date, t.id",
        params,
    )
    grouped: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for r in rows:
        if r["merchant"] in merchants:
            grouped[r["merchant"]].append((date.fromisoformat(r["d"]), r["amount"]))
    return grouped


def build_subscriptions(conn: sqlite3.Connection, windows: Windows) -> list[dict]:
    monthly = {hit["merchant"] for hit in find_recurring(conn) if hit["cadence"] == "monthly"}
    if not monthly:
        return []
    new_year, new_month = shift_month(windows.month_start.year, windows.month_start.month, -(SUBSCRIPTION_NEW_MONTHS - 1))
    new_cutoff = date(new_year, new_month, 1)
    deadline = windows.current_end - timedelta(days=SUBSCRIPTION_MISSING_GRACE_DAYS)

    items = []
    for merchant, charges in _charges(conn, monthly).items():
        in_window = [i for i, (when, _) in enumerate(charges) if windows.current_start <= when <= windows.current_end]
        before = [charge for charge in charges if charge[0] < windows.month_start]

        if in_window:
            latest = in_window[-1]
            if latest > 0:
                amount, previous = charges[latest][1], charges[latest - 1][1]
                difference = amount - previous
                if abs(difference) >= max(SUBSCRIPTION_MIN_CHANGE, previous * SUBSCRIPTION_MIN_PCT / 100):
                    items.append(_item(merchant, "price_up" if difference > 0 else "price_down", amount, previous))
        elif len(before) >= 2:
            gaps = [(later[0] - earlier[0]).days for earlier, later in zip(before, before[1:])]
            expected = before[-1][0] + timedelta(days=round(statistics.median(gaps)))
            if windows.current_start <= expected <= deadline:
                items.append(_item(merchant, "missing", None, before[-1][1], expected))

        if new_cutoff <= charges[0][0] <= windows.current_end:
            items.append(_item(merchant, "new", charges[in_window[-1]][1] if in_window else None, None))

    items.sort(key=lambda i: (KIND_ORDER[i["kind"]], i["merchant"]))
    return items
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/insights/subscriptions.py backend/tests/test_insights_subscriptions.py
git commit -m "feat: insights subscription changes" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Assemble the result and expose `GET /api/insights`

**Files:**
- Modify: `backend/finio/services/insights/__init__.py`, `backend/finio/deps.py`, `backend/finio/app.py`
- Create: `backend/finio/api/insights.py`, `backend/tests/test_insights_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces:
  - `build_insights(conn, month: str | None, today: date) -> dict` with keys `month`, `in_progress`, `as_of` (ISO today when in progress, else `None`), `days_elapsed`, `days_in_month`, `available_months` (months with counted spending that are not after the current month, ascending), `summary`, `movers`, `new_merchants`, `growing_merchants`, `unusual_charges`, `subscriptions`. When `month is None` the month is the current month if it has spending, else the latest available month, else (no data) the current month. Malformed/future months raise `ValidationFailed`.
  - `deps.get_today() -> date` (FastAPI dependency returning `date.today()`; tests override it).
  - `GET /api/insights?month=YYYY-MM` (router mounted under `/api` in `app.py`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_insights_api.py`:
```python
from datetime import date

from finio.deps import get_today
from tests.helpers import insert_txn

TOP_LEVEL = {"month", "in_progress", "as_of", "days_elapsed", "days_in_month", "available_months", "summary",
             "movers", "new_merchants", "growing_merchants", "unusual_charges", "subscriptions"}


def pin_today(client, day):
    client.app.dependency_overrides[get_today] = lambda: day


def seed(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000, merchant="Alpha", category="Grocery")
    insert_txn(conn, acct, date="2026-09-03", amount=30000, merchant="Alpha", category="Grocery")
    insert_txn(conn, acct, date="2026-09-04", amount=5000, merchant="Bravo", category="Restaurants")


def test_month_in_progress_end_to_end(client, conn, make_account):
    seed(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    r = client.get("/api/insights")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == TOP_LEVEL
    assert (d["month"], d["in_progress"], d["as_of"], d["days_elapsed"], d["days_in_month"]) == ("2026-09", True, "2026-09-20", 20, 30)
    assert d["available_months"] == ["2026-08", "2026-09"]
    assert d["summary"] == {"total": 35000, "compared_with": "Aug 1–20", "previous_total": 10000, "change": 25000,
                            "change_pct": 250.0, "typical_total": None, "rank": None, "projected_total": 52500}
    assert [(m["category"], m["change"], m["change_pct"]) for m in d["movers"]["up"]] == [("Grocery", 20000, 200.0), ("Restaurants", 5000, None)]
    assert d["movers"]["down"] == []
    assert d["new_merchants"] == [{"merchant": "Bravo", "total": 5000, "count": 1}]
    assert [g["merchant"] for g in d["growing_merchants"]] == ["Alpha"]
    assert d["unusual_charges"] == [] and d["subscriptions"] == []


def test_a_past_month_is_complete(client, conn, make_account):
    seed(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    d = client.get("/api/insights", params={"month": "2026-08"}).json()
    assert (d["month"], d["in_progress"], d["as_of"], d["days_elapsed"]) == ("2026-08", False, None, 31)
    assert d["summary"]["total"] == 10000 and d["summary"]["projected_total"] is None
    assert d["new_merchants"] == []      # August is the first month with data


def test_default_month_falls_back_to_the_latest_month_with_spending(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000)
    pin_today(client, date(2026, 9, 20))          # nothing spent yet in September
    d = client.get("/api/insights").json()
    assert (d["month"], d["in_progress"]) == ("2026-08", False)


def test_bad_months_are_rejected(client):
    pin_today(client, date(2026, 9, 20))
    bad = client.get("/api/insights", params={"month": "2026-9"})
    assert bad.status_code == 400 and "2026-09" in bad.json()["detail"]
    assert client.get("/api/insights", params={"month": "2026-10"}).status_code == 400
    assert client.get("/api/insights", params={"month": "nonsense"}).status_code == 400


def test_an_empty_database(client):
    pin_today(client, date(2026, 9, 20))
    d = client.get("/api/insights").json()
    assert (d["month"], d["available_months"]) == ("2026-09", [])
    assert d["summary"]["total"] == 0 and d["summary"]["typical_total"] is None
    assert d["movers"] == {"up": [], "down": []}
    assert d["new_merchants"] == [] and d["growing_merchants"] == [] and d["unusual_charges"] == [] and d["subscriptions"] == []


def test_months_after_today_are_not_offered(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000)
    insert_txn(conn, acct, date="2026-11-05", amount=99999)      # dated in the future
    pin_today(client, date(2026, 9, 20))
    assert client.get("/api/insights").json()["available_months"] == ["2026-08"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_insights_api.py -q`
Expected: FAIL (`ImportError: cannot import name 'get_today'`).

- [ ] **Step 3: Implement**

`backend/finio/deps.py`: add `from datetime import date` and
```python
def get_today() -> date:
    return date.today()
```

`backend/finio/services/insights/__init__.py`:
```python
import sqlite3
from datetime import date

from finio.services.insights.changes import (
    build_growing,
    build_movers,
    build_new_merchants,
    category_totals,
    merchant_totals,
)
from finio.services.insights.spending import monthly_totals, window_total
from finio.services.insights.subscriptions import build_subscriptions
from finio.services.insights.summary import build_summary
from finio.services.insights.unusual import build_unusual
from finio.services.insights.windows import build_windows, month_key


def build_insights(conn: sqlite3.Connection, month: str | None, today: date) -> dict:
    totals = monthly_totals(conn)
    current_key = month_key(today)
    available = [m for m in totals if m <= current_key]
    if month is None:
        month = current_key if current_key in totals else (available[-1] if available else current_key)

    w = build_windows(month, today)
    return {
        "month": w.month,
        "in_progress": w.in_progress,
        "as_of": today.isoformat() if w.in_progress else None,
        "days_elapsed": w.days_elapsed,
        "days_in_month": w.days_in_month,
        "available_months": available,
        "summary": build_summary(
            w, totals,
            window_total(conn, w.current_start, w.current_end),
            window_total(conn, w.previous_start, w.previous_end),
        ),
        "movers": build_movers(
            category_totals(conn, w.current_start, w.current_end),
            category_totals(conn, w.previous_start, w.previous_end),
        ),
        "new_merchants": build_new_merchants(conn, w),
        "growing_merchants": build_growing(
            merchant_totals(conn, w.current_start, w.current_end),
            merchant_totals(conn, w.previous_start, w.previous_end),
        ),
        "unusual_charges": build_unusual(conn, w),
        "subscriptions": build_subscriptions(conn, w),
    }
```

`backend/finio/api/insights.py`:
```python
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends

from finio.deps import get_conn, get_today
from finio.services.insights import build_insights

router = APIRouter()


@router.get("/insights")
def get_insights(
    month: str | None = None,
    today: date = Depends(get_today),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return build_insights(conn, month, today)
```

`backend/finio/app.py`: extend the wiring to include the new router:
```python
    from finio.api import accounts, analytics, categories, imports, insights, rules, transactions

    for module in (accounts, categories, imports, transactions, rules, analytics, insights):
        app.include_router(module.router, prefix="/api")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finio/services/insights/__init__.py backend/finio/deps.py backend/finio/app.py backend/finio/api/insights.py backend/tests/test_insights_api.py
git commit -m "feat: GET /api/insights" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend types, API call and wording helpers

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/api.test.ts`
- Create: `frontend/src/lib/insights.ts`, `frontend/src/lib/insights.test.ts`

**Interfaces:**
- Consumes: `formatCents` from `lib/money.ts`; `api.ts` `request` and `toQueryString`.
- Produces (types exported from `api.ts`):
  ```ts
  export type InsightRank = { position: number; of: number }
  export type InsightSummary = {
    total: number; compared_with: string; previous_total: number; change: number; change_pct: number | null
    typical_total: number | null; rank: InsightRank | null; projected_total: number | null
  }
  export type CategoryMover = { category: string; category_id: number; current: number; previous: number; change: number; change_pct: number | null }
  export type NewMerchant = { merchant: string; total: number; count: number }
  export type GrowingMerchant = { merchant: string; current: number; previous: number; change: number; change_pct: number | null }
  export type UnusualCharge = { transaction_id: number; date: string; merchant: string; category: string; amount: number; typical: number }
  export type SubscriptionKind = 'missing' | 'price_up' | 'price_down' | 'new'
  export type SubscriptionChange = { merchant: string; kind: SubscriptionKind; current: number | null; previous: number | null; expected_date: string | null }
  export type Insights = {
    month: string; in_progress: boolean; as_of: string | null; days_elapsed: number; days_in_month: number
    available_months: string[]; summary: InsightSummary
    movers: { up: CategoryMover[]; down: CategoryMover[] }
    new_merchants: NewMerchant[]; growing_merchants: GrowingMerchant[]
    unusual_charges: UnusualCharge[]; subscriptions: SubscriptionChange[]
  }
  ```
  and `api.insights(month?: string): Promise<Insights>`.
  Helpers in `lib/insights.ts`:
  - `monthLabel(key: string, inProgress = false): string` — `"2026-09"` → `"September 2026"`, with `" (in progress)"` appended when `inProgress`.
  - `neighborMonth(available: string[], month: string, step: 1 | -1): string | null` — `available` is ascending; returns the adjacent available month or `null` (also `null` when `month` is not in the list).
  - `formatPercent(pct: number): string` — `12 → "+12%"`, `-8.4 → "-8.4%"`, `12.0 → "+12%"` (drop a trailing `.0`), `0 → "0%"`.
  - `changeText(change: number, pct: number | null, comparedWith: string): string` — `"Up $212.00 (+12%) vs Aug 1–20"`, `"Down $50.00 (-5%) vs …"`, `"Same as …"` when `change === 0`; the percent part is left out when `pct` is `null`.
  - `paceText(daysElapsed: number, daysInMonth: number, projected: number | null): string` — `"Day 20 of 30 · on pace for $1,851.00"`; without the projection: `"Day 5 of 30"`.
  - `rankText(rank: InsightRank): string` — `"3rd highest of 9 months"`, `"1st highest of 4 months"` (ordinals: 1st, 2nd, 3rd, 4th…, 11th, 12th, 13th, 21st, 22nd).
  - `subscriptionTag(kind: SubscriptionKind): string` — `Price up`, `Price down`, `New`, `Missing`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/api.test.ts`:
```ts
describe('api.insights', () => {
  it('asks for the default month when none is given', async () => {
    await api.insights()
    expect(requested).toEqual(['/api/insights'])
  })

  it('sends the chosen month', async () => {
    await api.insights('2026-08')
    expect(requested).toEqual(['/api/insights?month=2026-08'])
  })
})
```

`frontend/src/lib/insights.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { changeText, formatPercent, monthLabel, neighborMonth, paceText, rankText, subscriptionTag } from './insights'

describe('monthLabel', () => {
  it('spells out the month', () => expect(monthLabel('2026-09')).toBe('September 2026'))
  it('marks a month in progress', () => expect(monthLabel('2026-09', true)).toBe('September 2026 (in progress)'))
})

describe('neighborMonth', () => {
  const months = ['2026-07', '2026-08', '2026-09']
  it('moves to the previous and the next available month', () => {
    expect(neighborMonth(months, '2026-08', -1)).toBe('2026-07')
    expect(neighborMonth(months, '2026-08', 1)).toBe('2026-09')
  })
  it('stops at the ends', () => {
    expect(neighborMonth(months, '2026-07', -1)).toBeNull()
    expect(neighborMonth(months, '2026-09', 1)).toBeNull()
  })
  it('skips months without spending and copes with an unknown month', () => {
    expect(neighborMonth(['2026-01', '2026-04'], '2026-04', -1)).toBe('2026-01')
    expect(neighborMonth(months, '2025-01', 1)).toBeNull()
  })
})

describe('formatPercent', () => {
  it('signs the number and drops a trailing .0', () => {
    expect(formatPercent(12)).toBe('+12%')
    expect(formatPercent(12.0)).toBe('+12%')
    expect(formatPercent(-8.4)).toBe('-8.4%')
    expect(formatPercent(0)).toBe('0%')
  })
})

describe('changeText', () => {
  it('says up, down or the same, in words', () => {
    expect(changeText(21200, 12, 'Aug 1–20')).toBe('Up $212.00 (+12%) vs Aug 1–20')
    expect(changeText(-5000, -5, 'August')).toBe('Down $50.00 (-5%) vs August')
    expect(changeText(0, 0, 'August')).toBe('Same as August')
  })
  it('leaves the percent out when there is nothing to divide by', () => {
    expect(changeText(5000, null, 'August')).toBe('Up $50.00 vs August')
  })
})

describe('paceText', () => {
  it('shows the pace once there is a projection', () => {
    expect(paceText(20, 30, 185100)).toBe('Day 20 of 30 · on pace for $1,851.00')
  })
  it('shows only the day early in the month', () => expect(paceText(5, 30, null)).toBe('Day 5 of 30'))
})

describe('rankText', () => {
  it('uses ordinals', () => {
    const t = (position: number) => rankText({ position, of: 9 })
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23].map(t)).toEqual([
      '1st highest of 9 months', '2nd highest of 9 months', '3rd highest of 9 months', '4th highest of 9 months',
      '11th highest of 9 months', '12th highest of 9 months', '13th highest of 9 months', '21st highest of 9 months',
      '22nd highest of 9 months', '23rd highest of 9 months',
    ])
  })
})

describe('subscriptionTag', () => {
  it('names every kind', () => {
    expect(['price_up', 'price_down', 'new', 'missing'].map((k) => subscriptionTag(k as never))).toEqual([
      'Price up', 'Price down', 'New', 'Missing',
    ])
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- --run`
Expected: FAIL (`./insights` not found; `api.insights` is not a function).

- [ ] **Step 3: Implement**

In `frontend/src/api.ts`, add the types listed under Interfaces (next to the other analytics types) and, inside the `api` object next to `recurring`:
```ts
  insights: (month?: string) => request<Insights>(`/insights${toQueryString({ month })}`),
```
(`toQueryString` already skips undefined values; if it does not, build the string with `month ? \`?month=${month}\` : ''`.)

`frontend/src/lib/insights.ts`:
```ts
import type { InsightRank, SubscriptionKind } from '../api'
import { formatCents } from './money'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export function monthLabel(key: string, inProgress = false): string {
  const [year, month] = key.split('-')
  return `${MONTHS[Number(month) - 1]} ${year}${inProgress ? ' (in progress)' : ''}`
}

export function neighborMonth(available: string[], month: string, step: 1 | -1): string | null {
  const at = available.indexOf(month)
  if (at === -1) return null
  return available[at + step] ?? null
}

export function formatPercent(pct: number): string {
  if (pct === 0) return '0%'
  const text = Number.isInteger(pct) ? String(pct) : pct.toFixed(1)
  return `${pct > 0 ? '+' : ''}${text}%`
}

export function changeText(change: number, pct: number | null, comparedWith: string): string {
  if (change === 0) return `Same as ${comparedWith}`
  const percent = pct === null ? '' : ` (${formatPercent(pct)})`
  return `${change > 0 ? 'Up' : 'Down'} ${formatCents(Math.abs(change))}${percent} vs ${comparedWith}`
}

export function paceText(daysElapsed: number, daysInMonth: number, projected: number | null): string {
  const day = `Day ${daysElapsed} of ${daysInMonth}`
  return projected === null ? day : `${day} · on pace for ${formatCents(projected)}`
}

function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

export function rankText(rank: InsightRank): string {
  return `${ordinal(rank.position)} highest of ${rank.of} months`
}

const TAGS: Record<SubscriptionKind, string> = {
  price_up: 'Price up',
  price_down: 'Price down',
  new: 'New',
  missing: 'Missing',
}

export function subscriptionTag(kind: SubscriptionKind): string {
  return TAGS[kind]
}
```
Note: with `-8.4`, `pct.toFixed(1)` gives `"-8.4"`; with `12.0`, `Number.isInteger` is true.

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npm test -- --run && ./node_modules/.bin/tsc -b`
Expected: all PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/api.test.ts frontend/src/lib/insights.ts frontend/src/lib/insights.test.ts
git commit -m "feat: insights api client and wording helpers" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: The Insights page

**Files:**
- Create: `frontend/src/components/InsightCard.tsx`, `frontend/src/pages/Insights.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `api.insights`, `Insights` types, helpers from Task 7, `useFetch` (`{ data, error, loading, reload }`), `formatCents`.
- Produces: `InsightCard` (props: `title: string; note: string; empty: string | null; children?: ReactNode` — renders a card with a heading, a one-line muted `note`, and either the `empty` message (when `empty` is not null) or the children); the `Insights` page; nav link `/insights` after Dashboard.

There is no browser test harness in this project, so the page is verified by type-check, the full Vitest run, and the browser check in Task 9.

- [ ] **Step 1: Add the card component**

`frontend/src/components/InsightCard.tsx`:
```tsx
import type { ReactNode } from 'react'

type Props = {
  title: string
  /** One line on how the card is worked out. */
  note: string
  /** Shown instead of the children when there is nothing to report. */
  empty: string | null
  children?: ReactNode
}

export default function InsightCard({ title, note, empty, children }: Props) {
  return (
    <section className="insight-card">
      <h2>{title}</h2>
      <p className="muted insight-note">{note}</p>
      {empty !== null ? <p className="muted">{empty}</p> : children}
    </section>
  )
}
```

- [ ] **Step 2: Add the page**

`frontend/src/pages/Insights.tsx`:
```tsx
import { useState } from 'react'
import { api, type CategoryMover, type Insights as InsightsData } from '../api'
import InsightCard from '../components/InsightCard'
import { changeText, formatPercent, monthLabel, neighborMonth, paceText, rankText, subscriptionTag } from '../lib/insights'
import { formatCents } from '../lib/money'
import { useFetch } from '../lib/useFetch'

function Movers({ title, items }: { title: string; items: CategoryMover[] }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">None</p>
      ) : (
        <ul className="insight-list">
          {items.map((m) => (
            <li key={m.category_id}>
              <span>{m.category}</span>
              <span className={m.change > 0 ? 'up' : 'down'}>
                {m.change > 0 ? '+' : '-'}
                {formatCents(Math.abs(m.change))} {m.change_pct === null ? '(new)' : `(${formatPercent(m.change_pct)})`}
              </span>
              <span className="muted">
                {formatCents(m.previous)} → {formatCents(m.current)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Glance({ data }: { data: InsightsData }) {
  const { summary } = data
  return (
    <section className="insight-glance">
      <div className="insight-total">
        {formatCents(summary.total)}
        {data.in_progress && <span className="muted"> so far</span>}
      </div>
      <p className={summary.change > 0 ? 'up' : summary.change < 0 ? 'down' : undefined}>
        {changeText(summary.change, summary.change_pct, summary.compared_with)}
      </p>
      <ul className="insight-facts">
        {summary.typical_total !== null && <li>A typical month: {formatCents(summary.typical_total)}</li>}
        {summary.rank !== null && <li>{rankText(summary.rank)}</li>}
        {data.in_progress && <li>{paceText(data.days_elapsed, data.days_in_month, summary.projected_total)}</li>}
        {summary.typical_total === null && <li className="muted">A typical month needs at least 3 other full months</li>}
      </ul>
    </section>
  )
}

export default function Insights() {
  const [month, setMonth] = useState<string | undefined>(undefined)
  const insights = useFetch(() => api.insights(month), [month])
  const data = insights.data

  const newest = data ? [...data.available_months].reverse() : []
  const previous = data ? neighborMonth(data.available_months, data.month, -1) : null
  const next = data ? neighborMonth(data.available_months, data.month, 1) : null

  return (
    <section className="insights-page">
      <div className="insights-header">
        <h1>Insights</h1>
        {data && data.available_months.length > 0 && (
          <div className="insights-picker">
            <button type="button" aria-label="Previous month" disabled={previous === null} onClick={() => previous && setMonth(previous)}>
              ←
            </button>
            <select aria-label="Month" value={data.month} onChange={(e) => setMonth(e.target.value)}>
              {newest.map((m) => (
                <option key={m} value={m}>
                  {monthLabel(m, data.in_progress && m === data.month)}
                </option>
              ))}
            </select>
            <button type="button" aria-label="Next month" disabled={next === null} onClick={() => next && setMonth(next)}>
              →
            </button>
          </div>
        )}
      </div>

      {insights.error ? (
        <p className="error">{insights.error}</p>
      ) : data === null ? (
        <p className="muted">Loading…</p>
      ) : data.available_months.length === 0 ? (
        <p className="muted">Import a statement to see insights.</p>
      ) : (
        <div className={insights.loading ? 'stale' : undefined}>
          <Glance data={data} />
          <div className="insight-grid">
            <InsightCard
              title="Biggest movers"
              note={`Category changes of $10 or more against ${data.summary.compared_with}.`}
              empty={data.movers.up.length === 0 && data.movers.down.length === 0 ? 'No big changes by category' : null}
            >
              <Movers title="Went up" items={data.movers.up} />
              <Movers title="Went down" items={data.movers.down} />
            </InsightCard>

            <InsightCard
              title="New merchants"
              note="Places you had not spent at before this month."
              empty={data.new_merchants.length === 0 ? 'No new merchants this month' : null}
            >
              <ul className="insight-list">
                {data.new_merchants.map((m) => (
                  <li key={m.merchant}>
                    <span>{m.merchant}</span>
                    <span>{formatCents(m.total)}</span>
                    <span className="muted">{m.count === 1 ? '1 visit' : `${m.count} visits`}</span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Merchants that grew"
              note="Up by $25 or more and at least 1.5 times last month."
              empty={data.growing_merchants.length === 0 ? 'No merchants grew sharply' : null}
            >
              <ul className="insight-list">
                {data.growing_merchants.map((m) => (
                  <li key={m.merchant}>
                    <span>{m.merchant}</span>
                    <span className="up">
                      +{formatCents(m.change)} {m.change_pct !== null && `(${formatPercent(m.change_pct)})`}
                    </span>
                    <span className="muted">
                      {formatCents(m.previous)} → {formatCents(m.current)}
                    </span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Unusual charges"
              note="At least 3 times the usual charge in that category, and $50 or more."
              empty={data.unusual_charges.length === 0 ? 'No unusual charges this month' : null}
            >
              <ul className="insight-list">
                {data.unusual_charges.map((u) => (
                  <li key={u.transaction_id}>
                    <span>
                      {u.merchant} <span className="muted">{u.date}</span>
                    </span>
                    <span>{formatCents(u.amount)}</span>
                    <span className="muted">
                      typical for {u.category}: {formatCents(u.typical)}
                    </span>
                  </li>
                ))}
              </ul>
            </InsightCard>

            <InsightCard
              title="Subscription changes"
              note="Monthly charges that changed price, started, or did not show up."
              empty={data.subscriptions.length === 0 ? 'No subscription changes' : null}
            >
              <ul className="insight-list">
                {data.subscriptions.map((s) => (
                  <li key={`${s.merchant}-${s.kind}`}>
                    <span>
                      {s.merchant} <span className={`tag tag-${s.kind}`}>{subscriptionTag(s.kind)}</span>
                    </span>
                    <span>
                      {s.kind === 'missing'
                        ? `expected ${s.expected_date}`
                        : s.previous !== null && s.current !== null
                          ? `${formatCents(s.previous)} → ${formatCents(s.current)}`
                          : s.current !== null
                            ? formatCents(s.current)
                            : ''}
                    </span>
                    <span className="muted">{s.kind === 'missing' && s.previous !== null ? `last ${formatCents(s.previous)}` : ''}</span>
                  </li>
                ))}
              </ul>
            </InsightCard>
          </div>
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 3: Wire the route and nav**

`frontend/src/App.tsx`: add `import Insights from './pages/Insights'`, insert `['/insights', 'Insights'],` after the Dashboard entry in `links`, and `<Route path="/insights" element={<Insights />} />` after the Dashboard route.

- [ ] **Step 4: Style it**

Append to `frontend/src/styles.css` (scoped under `.insights-page`):
```css
.insights-page .insights-header { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; justify-content: space-between; }
.insights-page .insights-picker { display: flex; gap: 0.5rem; align-items: center; }
.insights-page .insight-glance { background: #fff; border: 1px solid #e3e5e8; border-radius: 8px; padding: 1rem 1.25rem; margin: 0.75rem 0 1rem; }
.insights-page .insight-total { font-size: 2rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.insights-page .insight-facts { list-style: none; padding: 0; margin: 0.5rem 0 0; display: flex; flex-wrap: wrap; gap: 0.25rem 1.5rem; }
.insights-page .insight-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.insights-page .insight-card { background: #fff; border: 1px solid #e3e5e8; border-radius: 8px; padding: 0.75rem 1rem 1rem; }
.insights-page .insight-card h2 { margin: 0 0 0.15rem; font-size: 1.05rem; }
.insights-page .insight-card h3 { margin: 0.75rem 0 0.25rem; font-size: 0.85rem; color: #555; }
.insights-page .insight-note { margin: 0 0 0.5rem; font-size: 0.8rem; }
.insights-page .insight-list { list-style: none; padding: 0; margin: 0; }
.insights-page .insight-list li { display: grid; grid-template-columns: minmax(0, 1.4fr) auto minmax(0, 1.2fr); gap: 0.5rem; padding: 0.3rem 0; border-bottom: 1px solid #eceef1; font-variant-numeric: tabular-nums; }
.insights-page .insight-list li > :nth-child(3) { text-align: right; font-size: 0.85rem; }
.insights-page .up { color: #b25400; }
.insights-page .down { color: #0a7a3a; }
.insights-page .tag { font-size: 0.7rem; padding: 0.05rem 0.4rem; border-radius: 999px; background: #eceef1; color: #444; margin-left: 0.25rem; }
.insights-page .tag-price_up, .insights-page .tag-missing { background: #ffe9d6; color: #8a3f00; }
.insights-page .tag-price_down, .insights-page .tag-new { background: #dff4e6; color: #0a5a2a; }
@media (max-width: 720px) {
  .insights-page .insight-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 5: Verify**

Run: `cd frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build`
Expected: no type errors, all tests PASS, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InsightCard.tsx frontend/src/pages/Insights.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: Insights page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Docs and end-to-end check

**Files:**
- Modify: `docs/SPECIFICATION.md`, `docs/REQUIREMENTS.md`, `README.md`, `docs/TESTING.md`, `CLAUDE.md` (only the one-line layout note)

**Interfaces:** none new. Read each file first and match its existing style and numbering.

- [ ] **Step 1: Update the docs**

- `docs/SPECIFICATION.md`: add `GET /api/insights?month=YYYY-MM` to the API section (response shape and the default-month and 400 rules from the design spec `docs/specs/2026-09-21-insights-page-design.md`), and an "Insights" entry to the UI section (nav item, month picker, at-a-glance card, five cards, states).
- `docs/REQUIREMENTS.md`: continue the existing numbering (the last requirement is R38, confirm by reading the file) with new requirements for: the Insights page and month picker; month summary with same-days comparison, typical month, rank and pace; biggest movers; new merchants; merchants that grew; unusual charges; monthly subscription changes; insights counting only the user's share of purchases.
- `README.md`: add one feature bullet for the Insights page.
- `docs/TESTING.md`: add a short "Insights page" walkthrough (import or add transactions across at least three months, open Insights, change month, check each card and the empty states) and mention `tests/test_insights_*.py`.
- `CLAUDE.md`: in the Architecture list, add one line: `backend/finio/services/insights/`: the monthly insights (one small module per group of insights, thresholds in `constants.py`), assembled by `build_insights` behind `GET /api/insights`.

- [ ] **Step 2: Full automated check**

Run: `cd backend && .venv/bin/pytest -q` and `cd frontend && ./node_modules/.bin/tsc -b && npm test -- --run && npm run build`
Expected: everything passes.

- [ ] **Step 3: Browser check on a throwaway database**

Never use the user's real database or ports 8000/5173. Build a fabricated database, for example:
```bash
cd backend && FINIO_DB=/tmp/insights-check.sqlite3 .venv/bin/python - <<'EOF'
# create the schema, then insert ~4 months of fabricated purchases (grocery, restaurants, shopping),
# a monthly subscription whose price rises, one new merchant this month, and one large outlier charge
EOF
FINIO_DB=/tmp/insights-check.sqlite3 .venv/bin/uvicorn finio.main:app --port 8001
```
Run a temporary Vite config on port 5174 that proxies `/api` to `127.0.0.1:8001` (a copy of `vite.config.ts` in the scratchpad, not committed). Load the page in a browser at desktop and phone width and confirm: the nav item, month picker and arrows, the in-progress label and pace line, each of the five cards populated, an empty month showing the empty messages, the Loading…/error/dimmed states, and no console errors. Stop the throwaway servers and delete the temporary database and config afterwards.

- [ ] **Step 4: Commit**

```bash
git add docs/SPECIFICATION.md docs/REQUIREMENTS.md README.md docs/TESTING.md CLAUDE.md
git commit -m "docs: Insights page" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

| Spec section | Task |
|---|---|
| Definitions: spending, windows, same-days comparison, future/malformed months | 1, 2 |
| Month at a glance: total, change, typical, rank, projection | 2, 6 |
| Biggest movers, new merchants, merchants that grew | 3 |
| Unusual charges | 4 |
| Subscription changes | 5 |
| Named constants in one place | 1 |
| `GET /api/insights`, default month, 400s, empty database, `available_months` | 6 |
| UI: nav item, month picker, at-a-glance, five cards, states, notes | 7, 8 |
| Edge cases: first month, previous month empty, splits/$0 shares | 2, 3, 4, 6 |
| Docs (specification, requirements, README, testing) and browser check | 9 |
