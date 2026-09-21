from datetime import date

from finio.deps import get_today
from tests.helpers import insert_txn

TOP_LEVEL = {"month", "in_progress", "as_of", "days_elapsed", "days_in_month", "available_months", "summary",
             "movers", "new_merchants", "growing_merchants", "unusual_charges", "subscriptions"}


def pin_today(client, day):
    client.app.dependency_overrides[get_today] = lambda: day


def seed(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000, merchant="Alpha", category="Grocery")
    insert_txn(conn, acct, date="2026-09-03", amount=30000, merchant="Alpha", category="Grocery")
    insert_txn(conn, acct, date="2026-09-04", amount=5000, merchant="Bravo", category="Restaurants")


def test_month_in_progress_end_to_end(client, conn, make_account):
    seed(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    r = client.get("/api/insights")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == TOP_LEVEL
    assert (d["month"], d["in_progress"], d["as_of"], d["days_elapsed"], d["days_in_month"]) == ("2026-09", True, "2026-09-20", 20, 30)
    assert d["available_months"] == ["2026-08", "2026-09"]
    assert d["summary"] == {"total": 35000, "compared_with": "Aug 1–20", "previous_total": 10000, "change": 25000,
                            "change_pct": 250.0, "typical_total": None, "rank": None, "projected_total": 52500}
    assert [(m["category"], m["change"], m["change_pct"]) for m in d["movers"]["up"]] == [("Grocery", 20000, 200.0), ("Restaurants", 5000, None)]
    assert d["movers"]["down"] == []
    assert d["new_merchants"] == [{"merchant": "Bravo", "total": 5000, "count": 1}]
    assert [g["merchant"] for g in d["growing_merchants"]] == ["Alpha"]
    assert d["unusual_charges"] == [] and d["subscriptions"] == []


def test_a_past_month_is_complete(client, conn, make_account):
    seed(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    d = client.get("/api/insights", params={"month": "2026-08"}).json()
    assert (d["month"], d["in_progress"], d["as_of"], d["days_elapsed"]) == ("2026-08", False, None, 31)
    assert d["summary"]["total"] == 10000 and d["summary"]["projected_total"] is None
    assert d["new_merchants"] == []      # August is the first month with data


def test_default_month_falls_back_to_the_latest_month_with_spending(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000)
    pin_today(client, date(2026, 9, 20))          # nothing spent yet in September
    d = client.get("/api/insights").json()
    assert (d["month"], d["in_progress"]) == ("2026-08", False)


def test_bad_months_are_rejected(client):
    pin_today(client, date(2026, 9, 20))
    bad = client.get("/api/insights", params={"month": "2026-9"})
    assert bad.status_code == 400 and "2026-09" in bad.json()["detail"]
    assert client.get("/api/insights", params={"month": "2026-10"}).status_code == 400
    assert client.get("/api/insights", params={"month": "nonsense"}).status_code == 400


def test_an_empty_database(client):
    pin_today(client, date(2026, 9, 20))
    d = client.get("/api/insights").json()
    assert (d["month"], d["available_months"]) == ("2026-09", [])
    assert d["summary"]["total"] == 0 and d["summary"]["typical_total"] is None
    assert d["movers"] == {"up": [], "down": []}
    assert d["new_merchants"] == [] and d["growing_merchants"] == [] and d["unusual_charges"] == [] and d["subscriptions"] == []


def test_months_after_today_are_not_offered(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000)
    insert_txn(conn, acct, date="2026-11-05", amount=99999)      # dated in the future
    pin_today(client, date(2026, 9, 20))
    assert client.get("/api/insights").json()["available_months"] == ["2026-08"]


def test_bad_year_is_rejected(client):
    pin_today(client, date(2026, 9, 20))
    assert client.get("/api/insights", params={"month": "0000-01"}).status_code == 400


def test_a_valid_month_without_spending_is_empty(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000)
    insert_txn(conn, acct, date="2026-09-05", amount=20000)
    pin_today(client, date(2026, 9, 20))
    r = client.get("/api/insights", params={"month": "2026-07"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["month"] == "2026-07" and d["summary"]["total"] == 0
    assert d["movers"] == {"up": [], "down": []}
    assert d["new_merchants"] == [] and d["growing_merchants"] == [] and d["unusual_charges"] == [] and d["subscriptions"] == []


def seed_two_people(conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-07-05", amount=8000, merchant="Alpha", cardholder="Ann", category="Grocery")
    insert_txn(conn, acct, date="2026-08-05", amount=10000, merchant="Alpha", cardholder="Ann", category="Grocery")
    insert_txn(conn, acct, date="2026-08-06", amount=2000, merchant="Bravo", cardholder="Ben", category="Restaurants")
    insert_txn(conn, acct, date="2026-09-03", amount=30000, merchant="Alpha", cardholder="Ann", category="Grocery")
    insert_txn(conn, acct, date="2026-09-04", amount=5000, merchant="Bravo", cardholder="Ben", category="Restaurants")
    insert_txn(conn, acct, date="2026-09-05", amount=3000, merchant="Cafe", cardholder="Ben", category="Restaurants")


def test_cardholder_filters_every_insight(client, conn, make_account):
    seed_two_people(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    everyone = client.get("/api/insights").json()
    ann = client.get("/api/insights", params={"cardholder": "Ann"}).json()
    ben = client.get("/api/insights", params={"cardholder": "Ben"}).json()
    assert set(ann) == TOP_LEVEL
    assert everyone["summary"]["total"] == 38000
    assert (ann["summary"]["total"], ann["summary"]["previous_total"]) == (30000, 10000)
    assert (ben["summary"]["total"], ben["summary"]["previous_total"]) == (8000, 2000)
    assert ann["available_months"] == ["2026-07", "2026-08", "2026-09"]
    assert [m["category"] for m in ann["movers"]["up"]] == ["Grocery"]
    assert [m["category"] for m in ben["movers"]["up"]] == ["Restaurants"]
    assert [m["merchant"] for m in ben["new_merchants"]] == ["Cafe"]
    assert ann["new_merchants"] == []


def test_empty_cardholder_means_everyone(client, conn, make_account):
    seed_two_people(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    assert client.get("/api/insights", params={"cardholder": ""}).json() == client.get("/api/insights").json()


def test_default_month_uses_the_cardholders_months(client, conn, make_account):
    acct = make_account()
    insert_txn(conn, acct, date="2026-08-05", amount=10000, cardholder="Ann")
    insert_txn(conn, acct, date="2026-09-05", amount=20000, cardholder="Ben")
    pin_today(client, date(2026, 9, 20))
    assert client.get("/api/insights", params={"cardholder": "Ben"}).json()["month"] == "2026-09"
    ann = client.get("/api/insights", params={"cardholder": "Ann"}).json()
    assert (ann["month"], ann["in_progress"], ann["available_months"]) == ("2026-08", False, ["2026-08"])


def test_unknown_cardholder_is_an_empty_result(client, conn, make_account):
    seed_two_people(conn, make_account)
    pin_today(client, date(2026, 9, 20))
    r = client.get("/api/insights", params={"cardholder": "Nobody"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["month"], d["available_months"], d["summary"]["total"]) == ("2026-09", [], 0)
    assert d["movers"] == {"up": [], "down": []}
    assert d["new_merchants"] == [] and d["growing_merchants"] == [] and d["unusual_charges"] == [] and d["subscriptions"] == []
