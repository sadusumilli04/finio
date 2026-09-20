import sqlite3


def load_rules(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM category_rules ORDER BY priority, id").fetchall()


def rule_matches(rule, merchant: str | None, description: str | None) -> bool:
    field = merchant if rule["match_field"] == "merchant" else description
    haystack = (field or "").lower()
    pattern = rule["pattern"].lower()
    if rule["match_type"] == "equals":
        return haystack == pattern
    return pattern in haystack


def _other_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM categories WHERE name = 'Other'").fetchone()
    return row["id"] if row else conn.execute("SELECT MIN(id) AS id FROM categories").fetchone()["id"]


def resolve_category(
    conn: sqlite3.Connection,
    rules,
    merchant: str | None,
    description: str | None,
    source_category: str | None,
) -> tuple[int, str]:
    for rule in rules:
        if rule_matches(rule, merchant, description):
            return rule["category_id"], "rule"
    label = (source_category or "").strip()
    if label:
        row = conn.execute(
            "SELECT id FROM categories WHERE lower(name) = lower(?)", (label,)
        ).fetchone()
        if row:
            return row["id"], "source_default"
        cur = conn.execute("INSERT INTO categories(name) VALUES (?)", (label,))
        return cur.lastrowid, "source_default"
    return _other_id(conn), "source_default"


def reapply_rules(conn: sqlite3.Connection) -> int:
    """Re-derive the category of every non-manual row: rule match, else the import default."""
    rules = load_rules(conn)
    rows = conn.execute(
        "SELECT id, merchant_clean, raw_description, source_category, category_id, category_source "
        "FROM transactions WHERE category_source != 'manual'"
    ).fetchall()
    changed = 0
    with conn:
        for row in rows:
            category_id, source = resolve_category(
                conn, rules, row["merchant_clean"], row["raw_description"], row["source_category"]
            )
            if row["category_id"] != category_id or row["category_source"] != source:
                conn.execute(
                    "UPDATE transactions SET category_id = ?, category_source = ? WHERE id = ?",
                    (category_id, source, row["id"]),
                )
                changed += 1
    return changed
