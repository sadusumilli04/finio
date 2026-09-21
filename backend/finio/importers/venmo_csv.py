import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .base import ParseResult, RawTransaction, RowError

REQUIRED_COLUMNS = {"ID", "Datetime", "Type", "Status", "Amount (total)"}
FINAL_STATUSES = {"complete", "issued"}
TRANSFER_TYPES = {"standard transfer", "instant transfer"}
FRIENDS = "Friends & Family"
AMOUNT = re.compile(r"^([+-])\s*\$?\s*([\d,]+(?:\.\d{1,2})?)$")


def _signed_cents(value: str) -> tuple[str, int]:
    """Return the sign ("+" you received, "-" you paid) and the absolute amount in cents."""
    match = AMOUNT.match(value.strip())
    if not match:
        raise ValueError(f"invalid amount: {value.strip()!r}")
    try:
        cents = int((Decimal(match.group(2).replace(",", "")) * 100).to_integral_value())
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {value.strip()!r}") from exc
    return match.group(1), cents


def _find_header(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        cells = {c.strip() for c in row}
        if "ID" in cells and "Datetime" in cells:
            return index
    raise ValueError("Not a Venmo CSV; missing columns: ['Datetime', 'ID']")


class VenmoCsvImporter:
    def parse(self, content: bytes) -> ParseResult:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Not a Venmo CSV; the file is not UTF-8 text") from exc
        reader = csv.reader(io.StringIO(text))
        numbered = [(reader.line_num, row) for row in reader]
        header_at = _find_header([row for _, row in numbered])
        header = [c.strip() for c in numbered[header_at][1]]
        missing = REQUIRED_COLUMNS - set(header)
        if missing:
            raise ValueError(f"Not a Venmo CSV; missing columns: {sorted(missing)}")

        result = ParseResult()
        seen: set[str] = set()
        for line, cells in numbered[header_at + 1:]:
            row = dict(zip(header, cells))
            external_id = (row.get("ID") or "").strip()
            if not external_id or external_id in seen:
                continue
            try:
                result.rows.append(self._parse_row(row, external_id))
                seen.add(external_id)
            except ValueError as exc:
                result.errors.append(RowError(line=line, message=str(exc) or "invalid row"))
        return result

    def _parse_row(self, row: dict, external_id: str) -> RawTransaction:
        get = lambda key: (row.get(key) or "").strip()  # noqa: E731
        status = get("Status")
        if status.lower() not in FINAL_STATUSES:
            raise ValueError(f"status: {status or '(blank)'}")
        datetime_text = get("Datetime")
        try:
            date.fromisoformat(datetime_text[:10])
        except ValueError as exc:
            raise ValueError(f"invalid date: {datetime_text!r}") from exc
        sign, cents = _signed_cents(get("Amount (total)"))
        paid = sign == "-"
        amount = cents if paid else -cents

        kind = get("Type")
        lowered = kind.lower()
        note = get("Note")
        if lowered in TRANSFER_TYPES:
            type_, merchant, category, flagged = "transfer", "Venmo transfer", "Other", False
            fallback_note = kind
        else:
            if lowered == "charge":
                counterparty = get("From") if paid else get("To")
            else:
                counterparty = get("To") if paid else get("From")
            merchant, category = counterparty, FRIENDS
            fallback_note = f"Venmo {lowered}" if lowered else "Venmo transaction"
            if lowered in {"payment", "charge"}:
                type_, flagged = ("purchase" if paid else "payment"), False
            else:
                type_, flagged = "other", True

        return RawTransaction(
            transaction_date=datetime_text[:10],
            posted_date=None,
            amount=amount,
            type=type_,
            raw_description=note or fallback_note,
            merchant_raw=merchant,
            cardholder=None,
            source_category=category,
            raw_row={k: v for k, v in row.items() if k},
            flagged=flagged,
            external_id=external_id,
        )
