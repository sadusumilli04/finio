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


@pytest.mark.parametrize("bad", ["", "abc", "2026-9", "26-09", "2026-13", "2026-00", "2026/09", "2026-09-01",
                                 "0000-01", "1899-12", "202\u00b2-09", "\u0662\u0660\u0662\u0666-\u0660\u0669"])
def test_malformed_months_are_rejected(bad):
    with pytest.raises(ValidationFailed):
        parse_month(bad)


def test_helpers():
    assert parse_month("2026-09") == (2026, 9)
    assert month_key(date(2026, 9, 5)) == "2026-09"
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 9, -2) == (2026, 7)
    assert shift_month(2026, 12, 1) == (2027, 1)
