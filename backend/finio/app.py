import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from finio.db import connect, init_db
from finio.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from finio.services.demo_data import seed_demo_data

STATUS = {NotFoundError: 404, ForbiddenError: 403, ConflictError: 409, ValidationFailed: 400}

# backend/finio/app.py -> parents[2] is the repo root, in both the source tree and the Docker
# image (which mirrors the same backend/ + frontend/ + testdata/ layout).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATIC_DIR = REPO_ROOT / "frontend" / "dist"
DEFAULT_TESTDATA_DIR = REPO_ROOT / "testdata"


def _resolve_static_file(static_root: Path, full_path: str) -> Path | None:
    """The real file `full_path` refers to inside static_root, or None for a client-side
    route, a missing file, or an attempt to escape static_root."""
    candidate = (static_root / full_path).resolve()
    if candidate.is_file() and static_root.resolve() in candidate.parents:
        return candidate
    return None


def _mount_frontend(app: FastAPI, static_root: Path) -> None:
    """Serve the built frontend from the same origin as the API (used in the Docker image;
    local development still uses the Vite dev server, and this is never mounted there)."""

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        found = _resolve_static_file(static_root, full_path)
        return FileResponse(found or static_root / "index.html")


def create_app(
    db_path: str | Path | None = None,
    *,
    static_dir: str | Path | None = None,
    testdata_dir: str | Path | None = None,
) -> FastAPI:
    path = Path(db_path or os.environ.get("FINIO_DB", "data/finio.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    init_db(conn)
    if os.environ.get("FINIO_SEED_DEMO_DATA") == "1":
        seed_demo_data(conn, Path(testdata_dir) if testdata_dir is not None else DEFAULT_TESTDATA_DIR)
    conn.close()

    app = FastAPI(title="Finio")
    app.state.db_path = path

    def make_handler(status: int):
        async def handler(request: Request, exc: Exception):
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        return handler

    for exc_type, status in STATUS.items():
        app.add_exception_handler(exc_type, make_handler(status))

    from finio.api import accounts, analytics, categories, imports, insights, rules, transactions

    for module in (accounts, categories, imports, transactions, rules, analytics, insights):
        app.include_router(module.router, prefix="/api")

    static_root = Path(static_dir) if static_dir is not None else DEFAULT_STATIC_DIR
    if static_root.is_dir():
        _mount_frontend(app, static_root)

    return app
