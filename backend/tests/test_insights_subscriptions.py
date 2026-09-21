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


def test_price_down_item_fields(conn, make_account):
    acct = make_account()
    series(conn, acct, "Dropbox", monthly(10, range(3, 9)), [1200] * 5 + [1000])
    assert build_subscriptions(conn, AUG) == [
        {"merchant": "Dropbox", "kind": "price_down", "current": 1000, "previous": 1200, "expected_date": None}]


def test_a_new_item_without_a_charge_in_the_window_has_no_current(conn, make_account):
    acct = make_account()
    series(conn, acct, "Hulu", ["2026-07-03", "2026-08-03", "2026-09-03"], [1500] * 3)   # September's charge lands after "today"
    early = build_windows("2026-09", date(2026, 9, 2))
    new = [i for i in build_subscriptions(conn, early) if i["kind"] == "new"]
    assert new == [{"merchant": "Hulu", "kind": "new", "current": None, "previous": None, "expected_date": None}]


def test_subscriptions_are_per_cardholder(conn, make_account):
    acct = make_account()
    for d, a in zip(monthly(10, range(3, 9)), [1000] * 5 + [1200]):
        insert_txn(conn, acct, date=d, amount=a, merchant="Spotify", category="Entertainment", cardholder="Ann")
    for d in monthly(12, range(3, 9)):
        insert_txn(conn, acct, date=d, amount=1000, merchant="Netflix", category="Entertainment", cardholder="Ben")
    assert kinds(build_subscriptions(conn, AUG, cardholder="Ann")) == [("price_up", "Spotify")]
    assert build_subscriptions(conn, AUG, cardholder="Ben") == []
    assert kinds(build_subscriptions(conn, AUG)) == [("price_up", "Spotify")]
