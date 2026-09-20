from finio.services.recurring import detect
from tests.helpers import insert_txn


def test_monthly_detected():
    r = detect("Netflix", [("2026-07-15", 1549), ("2026-08-15", 1549), ("2026-09-14", 1549)])
    assert r == {
        "merchant": "Netflix", "cadence": "monthly", "typical_amount": 1549, "count": 3,
        "last_date": "2026-09-14", "next_expected": "2026-10-14",
    }


def test_monthly_with_short_and_long_months():
    dates = ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    assert detect("Rent Co", [(d, 100000) for d in dates])["cadence"] == "monthly"


def test_weekly_and_biweekly():
    weekly = [(f"2026-09-{d:02d}", 500) for d in (1, 8, 15, 22)]
    assert detect("Gym", weekly)["cadence"] == "weekly"
    biweekly = [("2026-08-01", 900), ("2026-08-15", 900), ("2026-08-29", 900)]
    assert detect("Payroll Fee", biweekly)["cadence"] == "biweekly"


def test_yearly():
    r = detect("Insurance", [("2024-03-01", 90000), ("2025-03-02", 90000), ("2026-03-01", 90000)])
    assert r["cadence"] == "yearly"


def test_too_few_occurrences():
    assert detect("X", [("2026-08-01", 500), ("2026-09-01", 500)]) is None


def test_same_day_duplicates_do_not_count_as_extra_occurrences():
    assert detect("X", [("2026-08-01", 500), ("2026-08-01", 500), ("2026-09-01", 500)]) is None


def test_irregular_gaps_rejected():
    assert detect("Grocer", [("2026-09-01", 500), ("2026-09-04", 500), ("2026-09-20", 500)]) is None


def test_wildly_varying_amounts_rejected():
    assert detect("Shop", [("2026-07-01", 500), ("2026-08-01", 5000), ("2026-09-01", 900)]) is None


def test_slightly_varying_amounts_accepted():
    r = detect("Utility", [("2026-07-01", 8000), ("2026-08-01", 9000), ("2026-09-01", 8500)])
    assert r is not None and r["typical_amount"] == 8500


def test_endpoint_groups_by_merchant_and_ignores_non_purchases(client, conn, make_account):
    acct = make_account()
    for d in ("2026-07-15", "2026-08-15", "2026-09-14"):
        insert_txn(conn, acct, date=d, amount=1549, merchant="Netflix", category="Entertainment")
    for d in ("2026-07-01", "2026-08-01", "2026-09-01"):
        insert_txn(conn, acct, date=d, amount=-5000, type="payment", merchant="Payment")
    insert_txn(conn, acct, date="2026-09-02", amount=700, merchant="One Off")
    data = client.get("/api/analytics/recurring").json()
    assert [d["merchant"] for d in data] == ["Netflix"]
    assert data[0]["cadence"] == "monthly"
