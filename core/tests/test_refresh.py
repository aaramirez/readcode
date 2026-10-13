import json
import os
import shutil
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.server import refresh_on_startup
from readcode.validate_cmd import is_stale, refresh_stale, validate_study

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "kb"
SHA = "074ec965eabffb43a0224ef9f1426515d2818975"


@pytest.fixture()
def kb(tmp_path):
    dest = tmp_path / "kb"
    shutil.copytree(EXAMPLE, dest)
    validate_study(dest, "fixture")  # fresh derived files
    return dest


def _snap(kb):
    return kb / "fixture" / "snapshots" / SHA


def _add_tour(kb):
    tour = {"schemaVersion": 1, "id": "nuevo", "title": "Nuevo",
            "description": "Ver [[ref:app/main.py#main]].",
            "steps": [{"path": "app/main.py", "range": [4, 7], "title": "t", "body": "x"}]}
    path = _snap(kb) / "tours" / "nuevo.json"
    kbio.atomic_write_json(path, tour)
    old = time.time() - 120  # the derived files predate the new tour
    for links in (kb / "fixture").rglob("links.json"):
        os.utime(links, (old, old))


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_fresh_kb_is_not_stale(kb):
    assert not is_stale(kb / "fixture")
    assert refresh_stale(kb) == []


def test_refresh_regenerates_stale_study(kb):
    _add_tour(kb)
    assert is_stale(kb / "fixture")
    assert refresh_stale(kb) == ["fixture"]
    assert "tours/nuevo.json" in _read(_snap(kb) / "links.json")["docs"]
    assert not is_stale(kb / "fixture")


def test_missing_links_is_stale(kb):
    (_snap(kb) / "links.json").unlink()
    assert refresh_stale(kb) == ["fixture"]
    assert (_snap(kb) / "links.json").is_file()


def test_derived_only_matches_full_validate(kb, tmp_path):
    full = tmp_path / "full"
    shutil.copytree(kb, full)
    validate_study(full, "fixture")
    for p in kb.rglob("links.json"):
        p.unlink()
    (_snap(kb) / "search.json").unlink()
    validate_study(kb, "fixture", derived_only=True)
    for rel in sorted(p.relative_to(full) for p in full.rglob("*") if p.name in ("links.json", "search.json")):
        assert (kb / rel).read_bytes() == (full / rel).read_bytes(), rel


def test_derived_only_preserves_issues(kb):
    issues = {"schemaVersion": 1, "issues": [
        {"file": "explain/app/main.py.json", "problem": "gen", "hint": "h", "source": "generator"},
        {"file": "tree.json", "problem": "old", "hint": "h", "source": "validate"}]}
    kbio.atomic_write_json(_snap(kb) / "issues.json", issues)
    validate_study(kb, "fixture", derived_only=True)
    assert _read(_snap(kb) / "issues.json") == issues


def test_cli_derived_only_exits_zero_despite_problems(kb):
    bad = _snap(kb) / "explain" / "app" / "main.py.json"
    bad.write_text("not json", encoding="utf-8")
    assert runner.invoke(app, ["validate", str(kb), "fixture"]).exit_code == 1
    r = runner.invoke(app, ["validate", str(kb), "fixture", "--derived-only"])
    assert r.exit_code == 0, r.output


def test_refresh_on_startup_warns_once_on_failure(kb, monkeypatch):
    import readcode.validate_cmd as vc

    def boom(_kb, **_):
        raise PermissionError("solo lectura")
    monkeypatch.setattr(vc, "refresh_stale", boom)
    msgs = []
    assert refresh_on_startup(kb, echo=msgs.append) == []
    assert len(msgs) == 1 and "solo lectura" in msgs[0]


class _FakeServer:
    server_address = ("127.0.0.1", 1)

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        pass


@pytest.mark.parametrize("flag,expect", [([], True), (["--no-refresh"], False)])
def test_serve_startup_refreshes_before_listening(kb, monkeypatch, flag, expect):
    import readcode.server as srv
    _add_tour(kb)
    seen = {}

    def fake_make(kb_dir, port=8765, **_):
        seen["links"] = _read(_snap(kb) / "links.json")["docs"]  # state when the server is built
        return _FakeServer()
    monkeypatch.setattr(srv, "make_server", fake_make)
    r = runner.invoke(app, ["serve", str(kb), "--no-open", *flag])
    assert r.exit_code == 0, r.output
    assert ("tours/nuevo.json" in seen["links"]) is expect
    assert ("fixture" in r.output) is expect


def _set_study_shas(kb, shas, name="fixture"):
    path = kb / name / "study.json"
    data = _read(path)
    data["snapshots"] = [{"sha": s, "date": "2025-01-01T00:00:00Z", "message": "m", "status": "partial"}
                         for s in shas]
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("evil", ["ABS", "../../victim", r"..\..\victim"])
def test_unsafe_shas_never_write_outside_snapshots(kb, tmp_path, evil):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "links.json").write_text("untouched", encoding="utf-8")
    sha = str(victim) if evil == "ABS" else evil
    _set_study_shas(kb, [SHA, sha])
    for p in (kb / "fixture").rglob("links.json"):
        os.utime(p, (time.time() - 120,) * 2)
    refresh_on_startup(kb, echo=lambda m: None)
    problems = validate_study(kb, "fixture")
    assert (victim / "links.json").read_text(encoding="utf-8") == "untouched"
    assert not (victim / "search.json").exists()
    assert any("safe 40-hex sha" in p["problem"] for p in problems)


def test_unsafe_sha_with_invalid_study_schema_still_skipped(kb, tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    path = kb / "fixture" / "study.json"
    data = _read(path)
    data["snapshots"] = [{"sha": str(victim)}]  # fails the schema: raw-JSON fallback path
    path.write_text(json.dumps(data), encoding="utf-8")
    validate_study(kb, "fixture")
    assert list(victim.iterdir()) == []


def test_refresh_isolates_a_broken_study(kb):
    broken = kb / "aaa-broken"
    broken.mkdir()
    (broken / "study.json").write_text("[1, 2]", encoding="utf-8")  # non-dict study.json
    worse = kb / "aab-worse"
    worse.mkdir()
    (worse / "study.json").write_text("{not json", encoding="utf-8")
    _add_tour(kb)
    msgs = []
    assert refresh_stale(kb, echo=msgs.append) == ["fixture"]
    assert "tours/nuevo.json" in _read(_snap(kb) / "links.json")["docs"]
    assert len(msgs) == 1 and "aab-worse" in msgs[0]  # the list one is merely "not stale"


def test_refresh_continues_after_exception(kb, monkeypatch):
    import readcode.validate_cmd as vc
    other = kb / "aaa-other"
    shutil.copytree(kb / "fixture", other)
    _add_tour(kb)
    real = vc.validate_study

    def flaky(k, name, **kw):
        if name == "aaa-other":
            raise PermissionError("solo lectura")
        return real(k, name, **kw)
    monkeypatch.setattr(vc, "validate_study", flaky)
    for p in other.rglob("links.json"):
        p.unlink()
    msgs = []
    assert refresh_stale(kb, echo=msgs.append) == ["fixture"]
    assert len(msgs) == 1 and "aaa-other" in msgs[0] and "solo lectura" in msgs[0]
