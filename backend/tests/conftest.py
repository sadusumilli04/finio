import pytest
from fastapi.testclient import TestClient

from finio.db import connect, init_db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "finio.sqlite3"


@pytest.fixture
def conn(db_path):
    c = connect(db_path)
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def make_account(conn):
    def _make(source="apple_card_csv", name="Test Card", type="credit_card"):
        cur = conn.execute(
            "INSERT INTO accounts(name, type, source) VALUES (?, ?, ?)", (name, type, source)
        )
        conn.commit()
        return cur.lastrowid

    return _make


@pytest.fixture
def client(db_path):
    from finio.app import create_app

    with TestClient(create_app(db_path)) as c:
        yield c
