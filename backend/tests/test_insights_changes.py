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


def test_changes_can_be_limited_to_one_cardholder(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-10", amount=1000, merchant="Alpha", cardholder="Ann", category="Grocery")
    insert_txn(conn, acct, date="2026-09-02", amount=5000, merchant="Alpha", cardholder="Ann", category="Grocery")
    insert_txn(conn, acct, date="2026-09-03", amount=3000, merchant="Bravo", cardholder="Ben", category="Other")
    insert_txn(conn, acct, date="2026-08-11", amount=2000, merchant="Charlie", cardholder="Ben", category="Other")
    w = build_windows("2026-09", date(2026, 9, 20))
    start, end = w.current_start, w.current_end
    assert {v["category"]: v["total"] for v in category_totals(conn, start, end, cardholder="Ann").values()} == {"Grocery": 5000}
    assert merchant_totals(conn, start, end, cardholder="Ben") == {"Bravo": {"total": 3000, "count": 1}}
    assert [m["merchant"] for m in build_new_merchants(conn, w, cardholder="Ben")] == ["Bravo"]
    assert build_new_merchants(conn, w, cardholder="Ann") == []
    # Alpha is old for Ann but new for Ben, who never went there before
    insert_txn(conn, acct, date="2026-09-04", amount=700, merchant="Alpha", cardholder="Ben")
    assert [m["merchant"] for m in build_new_merchants(conn, w, cardholder="Ben")] == ["Bravo", "Alpha"]
    assert build_new_merchants(conn, w) == [{"merchant": "Bravo", "total": 3000, "count": 1}]
