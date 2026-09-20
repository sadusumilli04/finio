import hashlib
from collections import Counter

from finio.importers.base import RawTransaction


def fingerprint(account_id: int, r: RawTransaction) -> str:
    parts = [
        str(account_id), r.transaction_date, r.posted_date or "",
        str(r.amount), r.raw_description,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def assign_occurrences(fps: list[str]) -> list[int]:
    seen: Counter[str] = Counter()
    out = []
    for fp in fps:
        seen[fp] += 1
        out.append(seen[fp])
    return out
