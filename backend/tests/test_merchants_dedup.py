from finio.importers.base import RawTransaction
from finio.services.dedup import assign_occurrences, fingerprint
from finio.services.merchants import clean_merchant, load_aliases


def raw(**over):
    base = dict(
        transaction_date="2026-09-18", posted_date="2026-09-19", amount=500, type="purchase",
        raw_description="COFFEE", merchant_raw="Coffee", cardholder="A",
        source_category="Restaurants", raw_row={},
    )
    base.update(over)
    return RawTransaction(**base)


def test_clean_merchant_collapses_whitespace():
    assert clean_merchant("  Flik Cafe Az       Qps ", []) == "Flik Cafe Az Qps"


def test_clean_merchant_alias_wins_case_insensitive():
    aliases = [("flik cafe", "Flik Cafe")]
    assert clean_merchant("FLIK   CAFE AZ QPS", aliases) == "Flik Cafe"


def test_clean_merchant_handles_none_like_empty():
    assert clean_merchant("", []) == ""


def test_load_aliases(conn):
    conn.execute("INSERT INTO merchant_aliases(pattern, clean_name) VALUES ('sq *', 'Square Vendor')")
    conn.commit()
    assert load_aliases(conn) == [("sq *", "Square Vendor")]


def test_fingerprint_stable_and_sensitive():
    a = fingerprint(1, raw())
    assert a == fingerprint(1, raw())
    assert a != fingerprint(2, raw())
    assert a != fingerprint(1, raw(amount=501))
    assert a != fingerprint(1, raw(transaction_date="2026-09-17"))
    assert a != fingerprint(1, raw(raw_description="TEA"))


def test_assign_occurrences_counts_repeats():
    assert assign_occurrences(["a", "b", "a", "a", "b"]) == [1, 1, 2, 3, 2]
