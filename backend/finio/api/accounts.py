import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from finio.deps import get_conn
from finio.services import accounts as svc

router = APIRouter()


class AccountIn(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["credit_card", "checking", "savings", "other"]
    source: Literal["apple_card_csv", "manual"]
    starting_balance: int = 0
    starting_balance_date: str | None = None


@router.get("/accounts")
def list_accounts(conn: sqlite3.Connection = Depends(get_conn)):
    return svc.list_accounts(conn)


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, conn: sqlite3.Connection = Depends(get_conn)):
    with conn:
        cur = conn.execute(
            "INSERT INTO accounts(name, type, source, starting_balance, starting_balance_date) "
            "VALUES (?,?,?,?,?)",
            (body.name.strip(), body.type, body.source, body.starting_balance, body.starting_balance_date),
        )
    return svc.get_account(conn, cur.lastrowid)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    svc.delete_account(conn, account_id)
    return Response(status_code=204)
