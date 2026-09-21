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
