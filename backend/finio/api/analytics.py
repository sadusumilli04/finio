import datetime as dt
import sqlite3

from fastapi import APIRouter, Depends, Query

from finio.deps import get_conn
from finio.services import analytics as svc

router = APIRouter(prefix="/analytics")


def common_filters(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: int | None = None,
    cardholder: str | None = None,
    category_id: int | None = None,
) -> dict:
    return dict(
        date_from=date_from, date_to=date_to, account_id=account_id,
        cardholder=cardholder, category_id=category_id,
    )


@router.get("/spending-by-category")
def spending_by_category(filters: dict = Depends(common_filters), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.spending_by_category(conn, **filters)


@router.get("/trends")
def trends(filters: dict = Depends(common_filters), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.spending_trends(conn, **filters)


@router.get("/top-merchants")
def top_merchants(
    limit: int = Query(10, ge=1, le=100),
    filters: dict = Depends(common_filters),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return svc.top_merchants(conn, limit=limit, **filters)
