from pathlib import Path

import pytest

from finio.importers.base import RawTransaction
from finio.importers.venmo_csv import VenmoCsvImporter
from finio.services.dedup import fingerprint

FIXTURE = (Path(__file__).parent / "fixtures" / "venmo_sample.csv").read_bytes()
HEADER = (
    b"Account Statement - (@x) ,,,,,\nAccount Activity,,,,,\n"
    b",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
)


def parse(content=FIXTURE):
    return VenmoCsvImporter().parse(content)


def by_id(result):
    return {r.external_id: r for r in result.rows}


def test_reads_only_transaction_rows_and_reports_the_cancelled_one():
    result = parse()
    assert len(result.rows) == 7                                # 8 transaction rows, one cancelled
    assert [e.message for e in result.errors] == ["status: Cancelled"]
    assert result.errors[0].line > 0
    assert "1000000000000000007" not in by_id(result)


def test_payment_you_send_is_a_purchase_to_the_payee():
    r = by_id(parse())["1000000000000000001"]
    assert (r.type, r.amount, r.merchant_raw, r.raw_description) == ("purchase", 2000, "Person One", "groceries")
    assert (r.transaction_date, r.posted_date, r.cardholder, r.source_category) == ("2026-09-10", None, None, "Friends & Family")
    assert r.flagged is False


def test_charge_you_pay_is_a_purchase_to_the_requester():
    r = by_id(parse())["1000000000000000002"]
    assert (r.type, r.amount, r.merchant_raw) == ("purchase", 900, "Person Two")


def test_money_you_receive_is_money_in():
    rows = by_id(parse())
    payment_in, charge_paid = rows["1000000000000000004"], rows["1000000000000000005"]
    assert (payment_in.type, payment_in.amount, payment_in.merchant_raw) == ("payment", -4100, "Person One")
    assert (charge_paid.type, charge_paid.amount, charge_paid.merchant_raw) == ("payment", -5652, "Person Three")


def test_standard_transfer_is_not_spending():
    r = by_id(parse())["1000000000000000003"]
    assert (r.type, r.amount, r.merchant_raw, r.raw_description, r.source_category) == (
        "transfer", 1900, "Venmo transfer", "Standard Transfer", "Other",
    )


def test_thousands_separators_and_blank_notes():
    rows = by_id(parse())
    assert rows["1000000000000000006"].amount == 125000
    assert rows["1000000000000000008"].raw_description == "Venmo payment"


def test_raw_row_keeps_the_original_row():
    r = by_id(parse())["1000000000000000001"]
    assert r.raw_row["ID"] == "1000000000000000001" and r.raw_row["Amount (total)"] == "- $20.00"


def test_unknown_type_is_flagged_and_kept():
    content = HEADER + b",2000000000000000001,2026-09-01T10:00:00,Weird Thing,Complete,x,A,B,- $3.00\n"
    (r,) = parse(content).rows
    assert (r.type, r.amount, r.flagged) == ("other", 300, True)


def test_repeated_id_in_one_file_is_kept_once():
    row = b",3000000000000000001,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,- $3.00\n"
    assert len(parse(HEADER + row + row).rows) == 1


def test_bad_rows_are_reported_and_the_rest_imported():
    good = b",4000000000000000001,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,- $3.00\n"
    bad_amount = b",4000000000000000002,2026-09-01T10:00:00,Payment,Complete,x,Me,Them,abc\n"
    bad_date = b",4000000000000000003,not-a-date,Payment,Complete,x,Me,Them,- $3.00\n"
    result = parse(HEADER + good + bad_amount + bad_date)
    assert len(result.rows) == 1 and len(result.errors) == 2


def test_wrong_file_is_rejected():
    apple = (Path(__file__).parent / "fixtures" / "apple_sample.csv").read_bytes()
    with pytest.raises(ValueError, match="Not a Venmo CSV"):
        parse(apple)


def test_fingerprint_uses_the_venmo_id_and_apple_is_unchanged():
    base = dict(transaction_date="2026-09-01", posted_date=None, amount=100, type="purchase",
                raw_description="x", merchant_raw="m", cardholder=None, source_category=None, raw_row={})
    a = RawTransaction(**base, external_id="111")
    same_id_other_details = RawTransaction(**{**base, "amount": 999, "raw_description": "y"}, external_id="111")
    other_id = RawTransaction(**base, external_id="222")
    assert fingerprint(1, a) == fingerprint(1, same_id_other_details)
    assert fingerprint(1, a) != fingerprint(1, other_id)
    assert fingerprint(1, a) != fingerprint(2, a)
    apple = RawTransaction(**base)
    assert fingerprint(1, apple) == fingerprint(1, RawTransaction(**base))
    assert fingerprint(1, apple) != fingerprint(1, a)
