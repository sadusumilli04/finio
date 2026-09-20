import datetime as dt
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator

from finio.deps import get_conn
from finio.services import transactions as svc

router = APIRouter()


@router.get("/transactions")
def list_transactions(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: int | None = None,
    cardholder: str | None = None,
    category_id: int | None = None,
    merchant: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    q: str | None = None,
    sort: Literal["date", "amount", "merchant"] = "date",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return svc.list_transactions(
        conn, sort=sort, order=order, limit=limit, offset=offset,
        date_from=date_from, date_to=date_to, account_id=account_id, cardholder=cardholder,
        category_id=category_id, merchant=merchant, min_amount=min_amount, max_amount=max_amount, q=q,
    )


@router.get("/cardholders")
def cardholders(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT DISTINCT cardholder FROM transactions WHERE cardholder IS NOT NULL AND cardholder != '' "
        "ORDER BY cardholder"
    )
    return [r["cardholder"] for r in rows]


@router.get("/merchants")
def merchants(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT DISTINCT merchant_clean FROM transactions WHERE merchant_clean IS NOT NULL "
        "AND merchant_clean != '' ORDER BY merchant_clean LIMIT 500"
    )
    return [r["merchant_clean"] for r in rows]


class ManualTransactionIn(BaseModel):
    account_id: int
    date: dt.date
    amount: int = Field(gt=0)
    direction: Literal["expense", "income", "refund"]
    merchant: str
    description: str | None = None
    cardholder: str | None = None
    category_id: int

    @field_validator("merchant")
    @classmethod
    def merchant_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("merchant is required")
        return v


class TransactionPatch(BaseModel):
    category_id: int | None = None
    date: dt.date | None = None
    amount: int | None = Field(default=None, gt=0)
    direction: Literal["expense", "income", "refund"] | None = None
    merchant: str | None = None
    description: str | None = None
    cardholder: str | None = None

    @field_validator("merchant")
    @classmethod
    def merchant_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("merchant cannot be blank")
        return v


@router.post("/transactions", status_code=201)
def create_transaction(body: ManualTransactionIn, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.create_manual(conn, body.model_dump())


@router.patch("/transactions/{transaction_id}")
def update_transaction(transaction_id: int, body: TransactionPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.update_transaction(conn, transaction_id, body.model_dump(exclude_unset=True))


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    svc.delete_transaction(conn, transaction_id)
    return Response(status_code=204)
