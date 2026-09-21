import sqlite3
from datetime import date

from fastapi import APIRouter, Depends

from finio.deps import get_conn, get_today
from finio.services.insights import build_insights

router = APIRouter()


@router.get("/insights")
def get_insights(
    month: str | None = None,
    today: date = Depends(get_today),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return build_insights(conn, month, today)
