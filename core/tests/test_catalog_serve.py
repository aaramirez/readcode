import http.client
import json
import os
import re
import threading

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


def get(server, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
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
