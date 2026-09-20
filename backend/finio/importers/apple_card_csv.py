import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import ParseResult, RawTransaction, RowError

REQUIRED_COLUMNS = {
    "Transaction Date", "Description", "Merchant", "Category", "Type", "Amount (USD)",
}
TYPE_MAP = {
    "purchase": "purchase",
    "installment": "purchase",
    "payment": "payment",
    "refund": "refund",
    "credit": "refund",
}
MONEY_IN_TYPES = {"payment", "refund"}


def _iso_date(value: str) -> str:
    return datetime.strptime(value.strip(), "%m/%d/%Y").date().isoformat()


def _cents(value: str) -> int:
    return int((Decimal(value.strip()) * 100).to_integral_value())


class AppleCardCsvImporter:
    def parse(self, content: bytes) -> ParseResult:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Not an Apple Card CSV; missing columns: {sorted(missing)}")

        result = ParseResult()
        for row in reader:
            line = reader.line_num
            try:
                result.rows.append(self._parse_row(row))
            except (ValueError, InvalidOperation) as exc:
                result.errors.append(RowError(line=line, message=str(exc) or "invalid row"))
        return result

    def _parse_row(self, row: dict) -> RawTransaction:
        get = lambda key: (row.get(key) or "").strip()  # noqa: E731
        transaction_date = _iso_date(get("Transaction Date"))
        posted = get("Clearing Date")
        posted_date = _iso_date(posted) if posted else None
        amount = _cents(get("Amount (USD)"))

        mapped = TYPE_MAP.get(get("Type").lower())
        flagged = mapped is None
        type_ = mapped or "other"
        if type_ in MONEY_IN_TYPES:
            amount = -abs(amount)

        return RawTransaction(
            transaction_date=transaction_date,
            posted_date=posted_date,
            amount=amount,
            type=type_,
            raw_description=row.get("Description") or "",
            merchant_raw=row.get("Merchant") or "",
            cardholder=get("Purchased By") or None,
            source_category=get("Category") or None,
            raw_row={k: v for k, v in row.items() if k is not None},
            flagged=flagged,
        )
