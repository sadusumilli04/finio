import datetime as dt
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query

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
