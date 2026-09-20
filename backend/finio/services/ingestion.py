import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from finio.errors import ConflictError, NotFoundError, ValidationFailed
from finio.importers.apple_card_csv import AppleCardCsvImporter
from finio.importers.base import RowError
from finio.services.dedup import assign_occurrences, fingerprint
from finio.services.merchants import clean_merchant, load_aliases
from finio.services.rules import load_rules, resolve_category

IMPORTERS = {"apple_card_csv": AppleCardCsvImporter()}


@dataclass
class ImportSummary:
    batch_id: int
    rows_total: int
    rows_added: int
    rows_skipped: int
    flagged: int
    errors: list[RowError] = field(default_factory=list)


def import_file(conn: sqlite3.Connection, account_id: int, filename: str, content: bytes) -> ImportSummary:
    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    importer = IMPORTERS.get(account["source"])
    if importer is None:
        raise ValidationFailed(f"Account '{account['name']}' has no file importer; add transactions manually")

    file_hash = hashlib.sha256(content).hexdigest()
    if conn.execute(
        "SELECT 1 FROM import_batches WHERE account_id = ? AND file_hash = ?", (account_id, file_hash)
    ).fetchone():
        raise ConflictError("This exact file was already imported for this account")

    try:
        result = importer.parse(content)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc

    aliases = load_aliases(conn)
    rules = load_rules(conn)
    fps = [fingerprint(account_id, r) for r in result.rows]
    occurrences = assign_occurrences(fps)

    added = skipped = 0
    with conn:
        batch_id = conn.execute(
            "INSERT INTO import_batches(account_id, filename, file_hash, imported_at) VALUES (?,?,?,?)",
            (account_id, filename, file_hash, datetime.now(UTC).isoformat()),
        ).lastrowid
        for raw, fp, occ in zip(result.rows, fps, occurrences):
            if conn.execute(
                "SELECT 1 FROM transactions WHERE fingerprint = ? AND occurrence = ?", (fp, occ)
            ).fetchone():
                skipped += 1
                continue
            merchant_clean = clean_merchant(raw.merchant_raw, aliases)
            category_id, category_source = resolve_category(
                conn, rules, merchant_clean, raw.raw_description, raw.source_category
            )
            conn.execute(
                "INSERT INTO transactions(account_id, batch_id, posted_date, transaction_date, amount, "
                "type, raw_description, merchant_raw, merchant_clean, cardholder, category_id, "
                "category_source, source_category, origin, fingerprint, occurrence, raw_row) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'import',?,?,?)",
                (account_id, batch_id, raw.posted_date, raw.transaction_date, raw.amount, raw.type,
                 raw.raw_description, raw.merchant_raw, merchant_clean, raw.cardholder, category_id,
                 category_source, raw.source_category, fp, occ, json.dumps(raw.raw_row)),
            )
            added += 1
        conn.execute(
            "UPDATE import_batches SET rows_total=?, rows_added=?, rows_skipped=? WHERE id=?",
            (len(result.rows), added, skipped, batch_id),
        )

    return ImportSummary(
        batch_id=batch_id,
        rows_total=len(result.rows),
        rows_added=added,
        rows_skipped=skipped,
        flagged=sum(1 for r in result.rows if r.flagged),
        errors=result.errors,
    )
