import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, UploadFile

from finio.deps import get_conn
from finio.services.ingestion import import_file

router = APIRouter()


@router.post("/imports")
async def upload_import(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    content = await file.read()
    summary = import_file(conn, account_id, file.filename or "upload.csv", content)
    return asdict(summary)
