import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from finio.db import connect, init_db
from finio.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed

STATUS = {NotFoundError: 404, ForbiddenError: 403, ConflictError: 409, ValidationFailed: 400}


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = Path(db_path or os.environ.get("FINIO_DB", "data/finio.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    init_db(conn)
    conn.close()

    app = FastAPI(title="Finio")
    app.state.db_path = path

    def make_handler(status: int):
        async def handler(request: Request, exc: Exception):
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        return handler

    for exc_type, status in STATUS.items():
        app.add_exception_handler(exc_type, make_handler(status))

    from finio.api import accounts, categories, imports

    for module in (accounts, categories, imports):
        app.include_router(module.router, prefix="/api")
    return app
