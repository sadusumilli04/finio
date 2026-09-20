import sqlite3

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from finio.deps import get_conn
from finio.errors import ConflictError, NotFoundError

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


@router.get("/categories")
def list_categories(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY name")]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, conn: sqlite3.Connection = Depends(get_conn)):
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
    in_use = conn.execute(
        "SELECT (SELECT COUNT(*) FROM transactions WHERE category_id = :i) + "
        "(SELECT COUNT(*) FROM category_rules WHERE category_id = :i) AS n", {"i": category_id},
    ).fetchone()["n"]
    if in_use:
        raise ConflictError("Category is used by transactions or rules; reassign them first")
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return Response(status_code=204)
