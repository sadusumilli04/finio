import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finio.deps import get_conn

router = APIRouter()


class AccountIn(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["credit_card", "checking", "savings", "other"]
    source: Literal["apple_card_csv", "manual"]
    starting_balance: int = 0
    starting_balance_date: str | None = None


@router.get("/accounts")
def list_accounts(conn: sqlite3.Connection = Depends(get_conn)):
    return [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY id")]


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        cur = conn.execute(
            "INSERT INTO accounts(name, type, source, starting_balance, starting_balance_date) "
            "VALUES (?,?,?,?,?)",
            (body.name.strip(), body.type, body.source, body.starting_balance, body.starting_balance_date),
        )
    return dict(conn.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone())
