import re
import sqlite3


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_merchant(raw: str | None, aliases: list[tuple[str, str]]) -> str:
    normalized = normalize_whitespace(raw)
    lowered = normalized.lower()
    for pattern, clean_name in aliases:
        if pattern.lower() in lowered:
            return clean_name
    return normalized


def load_aliases(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT pattern, clean_name FROM merchant_aliases ORDER BY id")
    return [(r["pattern"], r["clean_name"]) for r in rows]
