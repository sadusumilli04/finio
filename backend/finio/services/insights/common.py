import statistics


def median_cents(values: list[int]) -> int | None:
    """Median of amounts in cents, rounded to a whole cent; None for an empty list."""
    if not values:
        return None
    return int(round(statistics.median(values)))
