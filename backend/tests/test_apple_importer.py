from pathlib import Path

import pytest

from finio.importers.apple_card_csv import AppleCardCsvImporter

FIXTURE = Path(__file__).parent / "fixtures" / "apple_sample.csv"
HEADER = "Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By\n"


def parse(text: str):
    return AppleCardCsvImporter().parse(text.encode("utf-8"))


def test_parses_fixture():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    assert result.errors == []
    assert len(result.rows) == 6
    target = result.rows[0]
    assert target.transaction_date == "2026-09-18"
    assert target.posted_date == "2026-09-19"
    assert target.amount == 2977
    assert target.type == "purchase"
    assert target.merchant_raw == "Target"
    assert target.source_category == "Grocery"
    assert target.cardholder == "Test Person A"
    assert target.raw_row["Amount (USD)"] == "29.77"


def test_merchant_whitespace_preserved_in_raw():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    assert result.rows[1].merchant_raw == "Flik Cafe Az       Qps"


def test_payment_is_negative_and_typed():
    result = AppleCardCsvImporter().parse(FIXTURE.read_bytes())
    payment = result.rows[4]
    assert payment.type == "payment"
    assert payment.amount == -10000


def test_positive_payment_amount_is_normalized_negative():
    row = '09/01/2026,09/02/2026,"PAYMENT","Payment","Payment","Payment","50.00","A"\n'
    assert parse(HEADER + row).rows[0].amount == -5000


def test_refund_is_negative():
    row = '09/01/2026,09/02/2026,"REFUND","Shop","Shopping","Credit","12.00","A"\n'
    r = parse(HEADER + row).rows[0]
    assert (r.type, r.amount) == ("refund", -1200)


def test_unknown_type_flagged_as_other():
    row = '09/01/2026,09/02/2026,"X","Shop","Shopping","Mystery","12.00","A"\n'
    r = parse(HEADER + row).rows[0]
    assert r.type == "other" and r.flagged is True


def test_bad_rows_reported_with_line_numbers_and_skipped():
    text = (
        HEADER
        + '13/45/2026,09/02/2026,"X","Shop","Shopping","Purchase","5.00","A"\n'
        + '09/01/2026,09/02/2026,"X","Shop","Shopping","Purchase","abc","A"\n'
        + '09/01/2026,09/02/2026,"X","Shop","Shopping","Purchase","7.25","A"\n'
    )
    result = parse(text)
    assert [e.line for e in result.errors] == [2, 3]
    assert len(result.rows) == 1 and result.rows[0].amount == 725


def test_missing_clearing_date_is_none():
    row = '09/01/2026,,"X","Shop","Shopping","Purchase","5.00","A"\n'
    assert parse(HEADER + row).rows[0].posted_date is None


def test_missing_columns_raises():
    with pytest.raises(ValueError, match="Apple Card"):
        parse("a,b,c\n1,2,3\n")


def test_utf8_bom_handled():
    data = b"\xef\xbb\xbf" + FIXTURE.read_bytes()
    assert len(AppleCardCsvImporter().parse(data).rows) == 6
