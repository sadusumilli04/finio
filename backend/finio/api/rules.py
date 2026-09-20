import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, field_validator, model_validator

from finio.deps import get_conn
from finio.errors import NotFoundError, ValidationFailed
from finio.services.rules import reapply_rules

router = APIRouter()


def _not_blank(v: str | None) -> str | None:
    if v is not None and not v.strip():
        raise ValueError("must not be blank")
    return v.strip() if v is not None else v


class RuleIn(BaseModel):
    match_field: Literal["merchant", "description"]
    match_type: Literal["contains", "equals"]
    pattern: str
    category_id: int
    priority: int = 100

    _check_pattern = field_validator("pattern")(_not_blank)


class RulePatch(BaseModel):
    match_field: Literal["merchant", "description"] | None = None
    match_type: Literal["contains", "equals"] | None = None
    pattern: str | None = None
    category_id: int | None = None
    priority: int | None = None

    _check_pattern = field_validator("pattern")(_not_blank)

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        null_fields = [k for k in self.model_fields_set if getattr(self, k) is None]
        if null_fields:
            raise ValueError(f"Explicit nulls not allowed for: {', '.join(null_fields)}")
        return self


class AliasIn(BaseModel):
    pattern: str
    clean_name: str

    _check_pattern = field_validator("pattern")(_not_blank)
    _check_name = field_validator("clean_name")(_not_blank)


def _require_category(conn, category_id: int) -> None:
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise ValidationFailed(f"Category {category_id} does not exist")


def _get_rule(conn, rule_id: int) -> dict:
    row = conn.execute("SELECT * FROM category_rules WHERE id = ?", (rule_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Rule {rule_id} not found")
    return dict(row)


@router.get("/rules")
def list_rules(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM category_rules ORDER BY priority, id")]


@router.get("/rules/{rule_id}")
def get_rule(rule_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    return _get_rule(conn, rule_id)


@router.post("/rules/reapply")
def reapply(conn: sqlite3.Connection = Depends(get_conn)):
    return {"updated": reapply_rules(conn)}


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, conn: sqlite3.Connection = Depends(get_conn)):
    _require_category(conn, body.category_id)
    with conn:
        cur = conn.execute(
            "INSERT INTO category_rules(match_field, match_type, pattern, category_id, priority) VALUES (?,?,?,?,?)",
            (body.match_field, body.match_type, body.pattern, body.category_id, body.priority),
        )
    return _get_rule(conn, cur.lastrowid)


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, body: RulePatch, conn: sqlite3.Connection = Depends(get_conn)):
    current = _get_rule(conn, rule_id)
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if "category_id" in fields:
        _require_category(conn, fields["category_id"])
    merged = {**current, **fields}
    with conn:
        conn.execute(
            "UPDATE category_rules SET match_field=?, match_type=?, pattern=?, category_id=?, priority=? WHERE id=?",
            (merged["match_field"], merged["match_type"], merged["pattern"], merged["category_id"],
             merged["priority"], rule_id),
        )
    return _get_rule(conn, rule_id)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    _get_rule(conn, rule_id)
    with conn:
        conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
    return Response(status_code=204)


@router.get("/aliases")
def list_aliases(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM merchant_aliases ORDER BY id")]


@router.post("/aliases", status_code=201)
def create_alias(body: AliasIn, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        cur = conn.execute(
            "INSERT INTO merchant_aliases(pattern, clean_name) VALUES (?, ?)", (body.pattern, body.clean_name)
        )
    return dict(conn.execute("SELECT * FROM merchant_aliases WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    if conn.execute("SELECT 1 FROM merchant_aliases WHERE id = ?", (alias_id,)).fetchone() is None:
        raise NotFoundError(f"Alias {alias_id} not found")
    with conn:
        conn.execute("DELETE FROM merchant_aliases WHERE id = ?", (alias_id,))
    return Response(status_code=204)
