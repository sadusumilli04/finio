import sqlite3
import sys
from pathlib import Path

from finio.services.ingestion import import_file

# (name, account type, source, the testdata/ file to import)
ACCOUNTS = [
    ("Apple Card (sample)", "credit_card", "apple_card_csv", "apple_card_2025.csv"),
    ("Venmo (sample)", "other", "venmo_csv", "venmo_2025.csv"),
]


def seed_demo_data(conn: sqlite3.Connection, testdata_dir: Path) -> None:
    """Populate a brand-new, empty database with the fabricated sample statements in testdata/.

    A no-op once any account already exists, so this only ever runs on a genuinely fresh
    database (including across a Docker container restart with a persisted volume). Never
    raises: a problem seeding demo data should not stop the app from starting.
    """
    if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0:
        return
    for name, type_, source, filename in ACCOUNTS:
        path = Path(testdata_dir) / filename
        if not path.is_file():
            continue
        try:
            with conn:
                account_id = conn.execute(
                    "INSERT INTO accounts(name, type, source) VALUES (?, ?, ?)", (name, type_, source)
                ).lastrowid
            import_file(conn, account_id, filename, path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - demo data is a nice-to-have, never fatal
            print(f"finio: could not seed demo data from {filename}: {exc}", file=sys.stderr)
