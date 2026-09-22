from fastapi.testclient import TestClient

from finio.app import _resolve_static_file, create_app


def make_dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>Finio</body></html>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('hi')")
    return dist


def test_serves_index_at_root(tmp_path):
    dist = make_dist(tmp_path)
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=dist)) as c:
        r = c.get("/")
        assert r.status_code == 200 and "Finio" in r.text


def test_serves_a_real_asset_file(tmp_path):
    dist = make_dist(tmp_path)
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=dist)) as c:
        r = c.get("/assets/app.js")
        assert r.status_code == 200 and "console.log" in r.text


def test_unknown_client_route_falls_back_to_index(tmp_path):
    dist = make_dist(tmp_path)
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=dist)) as c:
        r = c.get("/insights")
        assert r.status_code == 200 and "Finio" in r.text


def test_unknown_api_route_still_returns_json_404(tmp_path):
    dist = make_dist(tmp_path)
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=dist)) as c:
        r = c.get("/api/nonexistent")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")


def test_real_api_routes_still_work_when_static_is_mounted(tmp_path):
    dist = make_dist(tmp_path)
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=dist)) as c:
        r = c.get("/api/accounts")
        assert r.status_code == 200 and r.json() == []


def test_no_static_mount_when_the_directory_does_not_exist(tmp_path):
    with TestClient(create_app(tmp_path / "db.sqlite3", static_dir=tmp_path / "no-such-dir")) as c:
        r = c.get("/some/client/route")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")


def test_resolve_static_file_blocks_path_traversal(tmp_path):
    static_root = tmp_path / "dist"
    static_root.mkdir()
    (static_root / "index.html").write_text("ok")
    (tmp_path / "secret.txt").write_text("nope")
    assert _resolve_static_file(static_root, "../secret.txt") is None
    assert _resolve_static_file(static_root, "index.html") == static_root / "index.html"
    assert _resolve_static_file(static_root, "missing.js") is None
