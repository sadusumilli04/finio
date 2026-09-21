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
