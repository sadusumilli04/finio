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
