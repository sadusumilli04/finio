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
