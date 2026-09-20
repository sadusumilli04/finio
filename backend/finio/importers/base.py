from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawTransaction:
    transaction_date: str
    posted_date: str | None
    amount: int
    type: str
    raw_description: str
    merchant_raw: str
    cardholder: str | None
    source_category: str | None
    raw_row: dict
    flagged: bool = False


@dataclass(frozen=True)
class RowError:
    line: int
    message: str


@dataclass
class ParseResult:
    rows: list[RawTransaction] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
