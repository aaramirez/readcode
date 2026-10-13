import http.client
import json
import os
import re
import threading
from urllib.parse import quote

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.schemas import validate
from readcode.server import make_server

runner = CliRunner()


def _study(kb, name, title, n_snaps, mtime):
    sd = kb / name
    snaps = [{"sha": str(i) * 40, "date": "2026-01-01T00:00:00Z", "message": "m",
              "status": "indexed"} for i in range(n_snaps)]
    kbio.atomic_write_json(sd / "study.json", {
        "schemaVersion": 1, "name": name, "title": title, "repo": {"url": f"u/{name}"},
        "language": "es", "exclude": [], "tools": {"graphify": False, "archify": False},
        "snapshots": snaps})
    extra = sd / "snapshots" / "x" / "tree.json"
    kbio.atomic_write_text(extra, "{}")
    os.utime(sd / "study.json", (mtime, mtime))
    os.utime(extra, (mtime + 60, mtime + 60))


def test_catalog_two_studies(tmp_path):
    kb = tmp_path / "kb"
    _study(kb, "zeta", "Zeta", 2, 1_700_000_000)
    _study(kb, "alpha", "Alpha", 0, 1_600_000_000)
    (kb / "not-a-study").mkdir()
    r = runner.invoke(app, ["catalog", str(kb)])
    assert r.exit_code == 0, r.output
    cat = kbio.read_json(kb / "catalog.json")
    assert validate("catalog", cat) == []
    assert [s["name"] for s in cat["studies"]] == ["alpha", "zeta"]
    zeta = cat["studies"][1]
    assert zeta == {"name": "zeta", "title": "Zeta", "repo": {"url": "u/zeta"},
                    "snapshots": 2, "updated": "2023-11-14T22:14:20Z"}
    assert cat["studies"][0]["snapshots"] == 0


@pytest.fixture()
def served(tmp_path):
    kb = tmp_path / "kb"
    kbio.atomic_write_json(kb / "catalog.json", {"schemaVersion": 1, "studies": []})
    kbio.atomic_write_text(kb / "demo" / "overview.md", "# Hola")
    (tmp_path / "secret").write_text("TOPSECRET", encoding="utf-8")
    viewer = tmp_path / "viewer_dist"
    server = make_server(kb, port=0, viewer_dir=viewer, quiet=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server, viewer
    server.shutdown()
    server.server_close()


def request(server, path, host=None):
    """GET ``path``; ``host`` overrides the Host header (None = http.client's default)."""
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    if host is None:
        conn.request("GET", path)
    else:
        conn.putrequest("GET", path, skip_host=True)
        if host != "":
            conn.putheader("Host", host)
        conn.endheaders()
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def get(server, path):
    resp, body = request(server, path)
    return resp.status, resp.getheader("Content-Type"), body


def test_serve_kb_json_and_md(served):
    server, _ = served
    status, ctype, body = get(server, "/kb/catalog.json")
    assert status == 200 and ctype.startswith("application/json")
    assert json.loads(body) == {"schemaVersion": 1, "studies": []}
    status, ctype, body = get(server, "/kb/demo/overview.md?x=1")
    assert status == 200 and ctype == "text/markdown; charset=utf-8" and body == b"# Hola"
    assert get(server, "/kb/missing.json")[0] == 404


@pytest.mark.parametrize("path", ["/kb/../secret", "/kb/%2e%2e/secret", "/kb/..%5csecret",
                                  "/../secret", "/kb//secret"])
def test_serve_blocks_traversal(served, path):
    server, _ = served
    status, _, body = get(server, path)
    assert status != 200 or b"TOPSECRET" not in body
    assert b"TOPSECRET" not in body


@pytest.mark.parametrize("path", [
    "/kb/C:/Windows/win.ini",
    "/kb/C:%5cWindows%5cwin.ini",
    "/kb/c:%2fWindows%2fwin.ini",
    "/kb/C:win.ini",
    "/kb/%5cWindows%5cwin.ini",
    "/kb/..%5c..%5csecret",
    "/kb/%5c%5c127.0.0.1%5cc$%5cWindows%5cwin.ini",
    "/kb///127.0.0.1/c$/Windows/win.ini",
    "/kb/%2f%2f127.0.0.1%2fc$%2fWindows%2fwin.ini",
    "/C:/Windows/win.ini",
    "/%5c%5c127.0.0.1%5cc$%5cWindows%5cwin.ini",
    "/kb/catalog.json::$DATA",
])
def test_serve_blocks_drive_backslash_and_unc_paths(served, path):
    server, viewer = served
    kbio.atomic_write_text(viewer / "index.html", "<!doctype html><p>viewer</p>")
    status, _, body = get(server, path)
    assert status in (403, 404), (path, status)
    assert b"TOPSECRET" not in body and b"[fonts]" not in body.lower()


def test_serve_secret_sibling_by_absolute_path(served, tmp_path):
    server, _ = served
    absolute = (tmp_path / "secret").resolve().as_posix()
    status, _, body = get(server, "/kb/" + quote(absolute))
    assert status in (403, 404) and b"TOPSECRET" not in body


@pytest.mark.parametrize("host", ["evil.example:{port}", "evil.example", "127.0.0.1:1",
                                  "localhost", "127.0.0.1.nip.io:{port}", ""])
def test_serve_rejects_foreign_host_header(served, host):
    server, _ = served
    port = server.server_address[1]
    resp, body = request(server, "/kb/catalog.json", host=host.format(port=port))
    assert resp.status == 403
    assert b"studies" not in body
    assert resp.getheader("X-Content-Type-Options") == "nosniff"


@pytest.mark.parametrize("host", ["127.0.0.1:{port}", "localhost:{port}", "LOCALHOST:{port}",
                                  "[::1]:{port}"])
def test_serve_accepts_loopback_host_header(served, host):
    server, _ = served
    resp, body = request(server, "/kb/catalog.json", host=host.format(port=server.server_address[1]))
    assert resp.status == 200 and b"studies" in body


def test_serve_security_headers(served):
    server, viewer = served
    kbio.atomic_write_text(viewer / "index.html", "<!doctype html><p>viewer</p>")
    kbio.atomic_write_text(viewer / "x.html", "<p>v</p>")
    kb_root = viewer.parent / "kb"  # see the `served` fixture
    kbio.atomic_write_text(kb_root / "demo" / "diagrams" / "a.html", "<script>1</script>")
    resp, _ = request(server, "/kb/demo/diagrams/a.html")
    assert resp.status == 200
    assert resp.getheader("Content-Security-Policy") == "sandbox allow-scripts"
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    for path in ("/", "/x.html", "/kb/catalog.json", "/kb/demo/overview.md", "/kb/missing.json"):
        resp, _ = request(server, path)
        assert resp.getheader("Content-Security-Policy") is None, path
        assert resp.getheader("X-Content-Type-Options") == "nosniff", path
    resp, _ = request(server, "/kb")
    assert resp.status == 301 and resp.getheader("X-Content-Type-Options") == "nosniff"


def test_serve_placeholder_then_viewer(served):
    server, viewer = served
    status, ctype, body = get(server, "/")
    assert status == 200 and ctype.startswith("text/html")
    assert re.search("visor no est.* compilado", body.decode("utf-8"))
    kbio.atomic_write_text(viewer / "index.html", "<!doctype html><p>viewer</p>")
    kbio.atomic_write_text(viewer / "assets" / "app.js", "console.log(1)")
    status, ctype, body = get(server, "/")
    assert status == 200 and b"viewer" in body
    status, ctype, _ = get(server, "/assets/app.js")
    assert status == 200 and ctype == "text/javascript; charset=utf-8"
