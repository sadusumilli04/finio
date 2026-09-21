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
