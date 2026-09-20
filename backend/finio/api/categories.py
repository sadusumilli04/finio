import sqlite3

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from finio.deps import get_conn
from finio.errors import ConflictError, NotFoundError, ValidationFailed

router = APIRouter()


class CategoryIn(BaseModel):
    name: str = Field(min_length=1)
    parent_id: int | None = None


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    parent_id: int | None = None


def _get(conn, category_id: int):
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Category {category_id} not found")
    return row


def _validate_parent(conn, parent_id: int | None, category_id: int | None = None):
    """Validate parent_id constraints: parent must exist with no parent, one level deep, no self-parent."""
    if parent_id is None:
        return

    # Check if parent exists
    parent = conn.execute("SELECT * FROM categories WHERE id = ?", (parent_id,)).fetchone()
    if parent is None:
        raise ValidationFailed(f"Parent category {parent_id} not found")

    # Check if trying to set self as parent
    if category_id is not None and parent_id == category_id:
        raise ConflictError("A category cannot be its own parent")

    # Parent must have no parent (one level deep)
    if parent["parent_id"] is not None:
        raise ValidationFailed(f"Parent category {parent_id} already has a parent; categories are one level deep")


@router.get("/categories")
def list_categories(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY name")]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, conn: sqlite3.Connection = Depends(get_conn)):
    # Validate parent if provided
    if body.parent_id is not None:
        _validate_parent(conn, body.parent_id)

    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO categories(name, parent_id) VALUES (?, ?)", (body.name.strip(), body.parent_id)
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("Category name already exists or parent is invalid") from exc
    return dict(_get(conn, cur.lastrowid))


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryPatch, conn: sqlite3.Connection = Depends(get_conn)):
    current = _get(conn, category_id)
    fields = body.model_dump(exclude_unset=True)
    name = (fields.get("name") or current["name"]).strip()
    parent = fields.get("parent_id", current["parent_id"])

    # Check if trying to rename "Other"
    if "name" in fields and name != current["name"] and current["name"] == "Other":
        raise ConflictError("The 'Other' category cannot be renamed")

    # Validate parent if being changed
    if "parent_id" in fields:
        # Check if category has children
        has_children = conn.execute(
            "SELECT COUNT(*) as n FROM categories WHERE parent_id = ?", (category_id,)
        ).fetchone()["n"]
        if has_children and parent is not None:
            raise ConflictError("A category with children cannot be given a parent")

        # Validate parent constraints
        if parent is not None:
            _validate_parent(conn, parent, category_id)

    try:
        with conn:
            conn.execute("UPDATE categories SET name = ?, parent_id = ? WHERE id = ?", (name, parent, category_id))
    except sqlite3.IntegrityError as exc:
        raise ConflictError("Category name already exists or parent is invalid") from exc
    return dict(_get(conn, category_id))


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    row = _get(conn, category_id)
    if row["name"] == "Other":
        raise ConflictError("The 'Other' category cannot be deleted")

    # Check if category has children
    has_children = conn.execute(
        "SELECT COUNT(*) as n FROM categories WHERE parent_id = ?", (category_id,)
    ).fetchone()["n"]
    if has_children:
        raise ConflictError("Category has child categories; reassign or delete them first")

    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM transactions WHERE category_id = :i) + "
        "(SELECT COUNT(*) FROM category_rules WHERE category_id = :i) AS n", {"i": category_id},
    ).fetchone()["n"]
    if in_use:
        raise ConflictError("Category is used by transactions or rules; reassign them first")
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return Response(status_code=204)
