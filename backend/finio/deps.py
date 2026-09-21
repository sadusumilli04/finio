from datetime import date

from fastapi import Request

from finio.db import connect


def get_conn(request: Request):
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_today() -> date:
    return date.today()
