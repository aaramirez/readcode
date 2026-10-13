"""readcode context / stale / mark (helpers for the /readcode skill)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.context_cmd import ContextError, file_context, format_context
from readcode.mark_cmd import MarkError, mark_study
from readcode.stale_cmd import StaleError, stale_docs

EXAMPLE_KB = Path(__file__).resolve().parents[2] / "examples" / "kb"
SHA1 = "b42f63fb2414b4d4d830af722a64255504a80ee8"
SHA2 = "074ec965eabffb43a0224ef9f1426515d2818975"

runner = CliRunner()


@pytest.fixture()
def kb(tmp_path):
    shutil.copytree(EXAMPLE_KB / "fixture", tmp_path / "fixture")
    return tmp_path


def test_context_on_example_snapshot():
    billing, missing = file_context(EXAMPLE_KB, "fixture", SHA2[:7],
                                    ["app/services/billing.py", "missing.py"])
    assert billing["lines"] == 15
    assert Path(billing["blobFile"]).is_absolute() and Path(billing["blobFile"]).is_file()
    assert billing["blobHash"] in billing["blobFile"]
    assert "refund (function) L13-15" in billing["defs"]
    assert billing["imports"] == ["app.models -> app/models.py"]
    assert billing["importedBy"] == ["app/main.py", "app/services/refunds.py"]
    assert billing["usedBy"]["app/services/refunds.py"] == ["refund"]
    assert any("app/services/refunds.py#process_refund" in n for n in billing["graphNeighbours"])
    assert billing["explanation"] == "current"
    assert missing == {"path": "missing.py", "error": "not in tree.json"}


def test_context_explanation_states(kb):
    snap = kbio.snapshot_dir(kb / "fixture", SHA2)
    doc = kbio.read_json(kbio.explain_path(snap, "app/models.py"))
    kbio.atomic_write_json(kbio.explain_path(snap, "app/models.py"), {**doc, "blobHash": "0" * 64})
    kbio.explain_path(snap, "app/main.py").unlink()
    states = {c["path"]: c["explanation"]
              for c in file_context(kb, "fixture", SHA2, ["app/models.py", "app/main.py"])}
    assert states == {"app/models.py": "stale", "app/main.py": "missing"}


def test_context_errors(tmp_path):
    with pytest.raises(ContextError, match="readcode init"):
        file_context(tmp_path, "nope", SHA2, ["x"])
    with pytest.raises(ContextError):
        file_context(EXAMPLE_KB, "fixture", "deadbeef", ["x"])


def test_context_cli():
    r = runner.invoke(app, ["context", str(EXAMPLE_KB), "fixture", "--sha", SHA2,
                            "app/services/billing.py", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)[0]["path"] == "app/services/billing.py"
    r = runner.invoke(app, ["context", str(EXAMPLE_KB), "fixture", "--sha", SHA2, "app/main.py"])
    assert r.exit_code == 0 and r.stdout.startswith("app/main.py (python")
    r = runner.invoke(app, ["context", str(EXAMPLE_KB), "fixture", "--sha", "deadbeef", "x"])
    assert r.exit_code == 1


def test_stale_on_example_update():
    out = stale_docs(EXAMPLE_KB, "fixture", SHA1[:7], SHA2[:7])
    assert (out["from"], out["to"]) == (SHA1, SHA2)
    # only definitions whose text changed; compute_total/process are untouched
    assert out["changedSymbols"] == {
        "app/services/billing.py": ["refund"],
        "app/services/refunds.py": ["process_refund"],
        "web/src/api.ts": ["refundInvoice"],
    }
    explain = {e["path"]: e for e in out["explain"]}
    assert "app/services/billing.py" not in explain  # changed files are re-explained, not refreshed
    assert explain["app/models.py"] == {"path": "app/models.py", "symbols": [], "markers": [
        "app/services/billing.py#refund", "app/services/refunds.py#process_refund"]}
    assert out["dirs"] == [{"path": "app/services", "markers": ["app/services/billing.py#refund"]}]
    tours = {t["id"]: t for t in out["tours"]}
    assert tours["flujo-facturacion"]["steps"] == [3, 6, 7]
    assert "worker-cola" not in tours
    # [[ref:app/services/billing.py#process]] is not flagged: process did not change
    assert out["overview"] == ["app/services/billing.py#refund",
                               "app/services/refunds.py#process_refund"]


def test_stale_reports_root_summary_from_dir_root(kb):
    snap = kbio.snapshot_dir(kb / "fixture", SHA2)
    path = snap / "dir-root.json"
    assert path.is_file()
    doc = kbio.read_json(path)
    doc["summary"] += " Ver [[ref:app/services/billing.py#refund]]."
    kbio.atomic_write_json(path, doc)
    out = stale_docs(kb, "fixture", SHA1[:7], SHA2[:7])
    assert {"path": "", "markers": ["app/services/billing.py#refund"]} in out["dirs"]


def test_stale_flags_code_refs_line_markers_and_unpathed(kb):
    snap2 = kbio.snapshot_dir(kb / "fixture", SHA2)
    syms = kbio.read_json(snap2 / "symbols.json")
    for d in syms["files"]["app/services/billing.py"]["defs"]:
        if d["name"] == "process":
            d["range"] = [7, 10]  # different text than in the old snapshot
    kbio.atomic_write_json(snap2 / "symbols.json", syms)
    worker = kbio.explain_path(snap2, "worker/queue.go")
    doc = kbio.read_json(worker)
    doc["summary"] += (" Ver [[ref:app/services/billing.py:L1-2]] y [[ref:#process]];"
                       " no `[[ref:app/services/refunds.py#process_refund]]`.")
    kbio.atomic_write_json(worker, doc)
    out = stale_docs(kb, "fixture", SHA1, SHA2)
    assert "process" in out["changedSymbols"]["app/services/billing.py"]
    explain = {e["path"]: e for e in out["explain"]}
    assert explain["app/main.py"]["symbols"] == ["process"]  # main.py calls billing.process
    # marker inside inline code is ignored (refs.parse_markers semantics)
    assert explain["worker/queue.go"]["markers"] == ["#process", "app/services/billing.py"]


def test_stale_needs_diff(kb):
    shutil.rmtree(kb / "fixture" / "diffs")
    with pytest.raises(StaleError, match="readcode diff"):
        stale_docs(kb, "fixture", SHA1, SHA2)
    r = runner.invoke(app, ["stale", str(kb), "fixture", SHA1, SHA2])
    assert r.exit_code == 1


def test_stale_cli():
    r = runner.invoke(app, ["stale", str(EXAMPLE_KB), "fixture", SHA1, SHA2, "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["to"] == SHA2
    r = runner.invoke(app, ["stale", str(EXAMPLE_KB), "fixture", SHA1, SHA2])
    assert r.exit_code == 0 and "explain app/models.py" in r.stdout


def test_mark_status_and_archify(kb):
    data = mark_study(kb, "fixture", sha=SHA1[:7], status="partial")
    assert data["snapshots"][0]["status"] == "partial"
    data = mark_study(kb, "fixture", archify=False)
    assert data["tools"] == {"graphify": True, "archify": False}
    stored = kbio.read_json(kb / "fixture" / "study.json")
    assert stored["snapshots"][0]["status"] == "partial" and stored["tools"]["archify"] is False


@pytest.mark.parametrize("kwargs, match", [
    ({}, "nothing to mark"),
    ({"status": "explained"}, "together"),
    ({"sha": SHA1}, "together"),
    ({"sha": SHA1, "status": "done"}, "one of"),
    ({"sha": "deadbeef", "status": "explained"}, None),
])
def test_mark_errors(kb, kwargs, match):
    before = (kb / "fixture" / "study.json").read_bytes()
    with pytest.raises(MarkError, match=match):
        mark_study(kb, "fixture", **kwargs)
    assert (kb / "fixture" / "study.json").read_bytes() == before


def test_mark_cli(kb):
    r = runner.invoke(app, ["mark", str(kb), "fixture", "--sha", SHA2, "--status", "partial",
                            "--archify", "false"])
    assert r.exit_code == 0, r.output
    data = kbio.read_json(kb / "fixture" / "study.json")
    assert data["snapshots"][1]["status"] == "partial" and data["tools"]["archify"] is False
    r = runner.invoke(app, ["mark", str(kb), "fixture", "--archify", "maybe"])
    assert r.exit_code == 1
    r = runner.invoke(app, ["mark", str(kb), "fixture"])
    assert r.exit_code == 1


def _stale_study(tmp_path, old: bytes, new: bytes, def_range):
    from readcode.snapshot import count_lines

    kb, sd = tmp_path / "kb", tmp_path / "kb" / "demo"
    a, b = "a" * 40, "b" * 40
    kbio.atomic_write_json(sd / "study.json", {
        "schemaVersion": 1, "name": "demo", "title": "D", "repo": {"url": "x"},
        "language": "es", "exclude": [], "tools": {"graphify": False, "archify": False},
        "snapshots": [{"sha": a, "date": "2026-01-01T00:00:00Z", "message": "1", "status": "indexed"},
                      {"sha": b, "date": "2026-01-02T00:00:00Z", "message": "2", "status": "indexed"}]})
    hashes = {}
    for sha, data in ((a, old), (b, new)):
        h = hashes[sha] = kbio.sha256_hex(data)
        kbio.atomic_write_bytes(kbio.blob_path(sd, h), data)
        snap = kbio.snapshot_dir(sd, sha)
        kbio.atomic_write_json(snap / "tree.json", {
            "schemaVersion": 1, "sha": sha, "excluded": [], "files": [
                {"path": "m.py", "blob": h, "language": "python", "lines": count_lines(data),
                 "bytes": len(data), "indexed": True}]})
        kbio.atomic_write_json(snap / "symbols.json", {"schemaVersion": 1, "sha": sha, "files": {
            "m.py": {"defs": [{"name": "f", "kind": "function", "range": def_range}],
                     "refs": [], "imports": []}}})
    kbio.atomic_write_json(sd / "diffs" / f"{a}..{b}" / "changes.json", {
        "schemaVersion": 1, "from": a, "to": b, "files": [
            {"path": "m.py", "status": "modified", "fromBlob": hashes[a], "toBlob": hashes[b],
             "hunks": [{"fromRange": [1, 1], "toRange": [1, 1], "header": "@@ -1,1 +1,1 @@"}]}]})
    return kb, sd, a, b, hashes


def test_stale_def_texts_use_newline_only_lines(tmp_path):
    # f is line 2 ("def f") in both; only line 1 changed. Splitting on the lone \r or on
    # U+2028 / \x85 / \f would shift "line 2" into the changed text.
    old = "x\ry = 1\u2028\x85\f\ndef f\n".encode("utf-8")
    new = "x\rz = 2\u2028\x85\f\ndef f\n".encode("utf-8")
    kb, _, a, b, _ = _stale_study(tmp_path, old, new, [2, 2])
    assert stale_docs(kb, "demo", a, b)["changedSymbols"] == {}
    kb2, _, a, b, _ = _stale_study(tmp_path / "2", old, "x\ry\ndef g\n".encode(), [2, 2])
    assert stale_docs(kb2, "demo", a, b)["changedSymbols"] == {"m.py": ["f"]}


def test_stale_missing_blob_is_a_clean_error(tmp_path):
    kb, sd, a, b, hashes = _stale_study(tmp_path, b"a\ndef f\n", b"b\ndef f\n", [2, 2])
    kbio.blob_path(sd, hashes[a]).unlink()
    with pytest.raises(StaleError, match="unreadable"):
        stale_docs(kb, "demo", a, b)
    r = runner.invoke(app, ["stale", str(kb), "demo", a, b])
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert "error:" in r.output


@pytest.mark.parametrize("content", [
    "{not json",
    '{"schemaVersion": 1, "from": "x", "to": "y", "files": [{"status": "modified"}]}',
    "[]",
])
def test_stale_malformed_changes_is_a_clean_error(tmp_path, content):
    kb, sd, a, b, _ = _stale_study(tmp_path, b"a\ndef f\n", b"b\ndef f\n", [2, 2])
    kbio.atomic_write_text(sd / "diffs" / f"{a}..{b}" / "changes.json", content)
    with pytest.raises(StaleError, match="readcode diff"):
        stale_docs(kb, "demo", a, b)
    r = runner.invoke(app, ["stale", str(kb), "demo", a, b])
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit)
    assert "error:" in r.output


def test_stale_resolves_pathless_line_markers_against_the_owning_file(tmp_path):
    kb, sd, a, b, _ = _stale_study(tmp_path, b"x = 1\ndef f\n", b"x = 2\ndef f\n", [2, 2])
    snap = kbio.snapshot_dir(sd, b)
    kbio.atomic_write_json(kbio.explain_path(snap, "m.py"), {
        "summary": "Mira [[ref::L1-1]] y `[[ref::L2]]`.", "blocks": []})
    kbio.atomic_write_json(snap / "dir-root.json", {"summary": "Raiz [[ref::L1-1]]."})
    out = stale_docs(kb, "demo", a, b)
    assert out["explain"] == [{"path": "m.py", "symbols": [], "markers": ["m.py"]}]
    assert out["dirs"] == []  # path-less line markers are forbidden (and ignored) outside explain docs


# ------------------------------------------------------------------ Go packages

import subprocess

GO_FILES = {
    "go.mod": "module github.com/x/y\n\ngo 1.22\n",
    "main.go": 'package main\n\nimport "github.com/x/y/internal/app"\n\nfunc main() { app.New().Start() }\n',
    "main_test.go": 'package main\n\nimport "github.com/x/y/internal/app"\n\nfunc TestMain() { app.New() }\n',
    "internal/app/app.go": 'package app\n\ntype App struct{}\n\nfunc New() *App { return &App{} }\n\n'
                           'func (a *App) Start() {}\n\nfunc helper() {}\n',
    "internal/app/util.go": 'package app\n\nvar ErrX = 1\n',
    "internal/app/app_test.go": 'package app\n\nfunc TestX() {}\n',
    "internal/many/many.go": "package many\n\n" + "".join(f"func f{i:03d}() {{}}\n" for i in range(45)),
    "internal/many/big.go": "package many\n\n" + "".join(f"func F{i:03d}() {{}}\n" for i in range(45)),
}


def _go_kb(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                                    text=True).stdout.strip()
    git("init", "-q")
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    sha = git("rev-parse", "HEAD")
    kb = tmp_path / "kb"
    for args in (("init", str(kb), "demo", "--repo", str(repo)),
                 ("snapshot", str(kb), "demo", "--sha", sha),
                 ("index", str(kb), "demo", "--sha", sha)):
        r = runner.invoke(app, list(args))
        assert r.exit_code == 0, r.output
    return kb, sha


def test_context_go_package_importers_and_neighbour_defs(tmp_path):
    kb, sha = _go_kb(tmp_path, GO_FILES)
    ctx = {c["path"]: c for c in file_context(
        kb, "demo", sha, ["internal/app/app.go", "main.go", "internal/app/app_test.go"])}
    app_go, main_go = ctx["internal/app/app.go"], ctx["main.go"]
    # imported by folder (resolvedDir); the test file counts only for test importers
    assert app_go["importedBy"] == ["main.go", "main_test.go"]
    assert ctx["internal/app/app_test.go"]["importedBy"] == ["main_test.go"]
    assert "github.com/x/y/internal/app -> internal/app/" in main_go["imports"]
    nd = main_go["neighbourDefs"]
    assert "internal/app/app.go#App.Start (method) L7-7" in nd or any(
        n.startswith("internal/app/app.go#App.Start (method)") for n in nd)
    assert any(n.startswith("internal/app/app.go#New (function)") for n in nd)
    assert any(n.startswith("internal/app/util.go#ErrX") for n in nd)
    assert not any("app_test.go" in n for n in nd)  # main.go is not a test
    assert main_go["truncated"] is False
    # exported before unexported inside a neighbour file
    app_defs = [n for n in nd if n.startswith("internal/app/app.go#")]
    assert app_defs[-1].startswith("internal/app/app.go#helper")
    # same-package neighbours, test file included only for a test file
    assert any(n.startswith("internal/app/app.go#") for n in ctx["internal/app/app_test.go"]["neighbourDefs"])
    assert not any("app_test.go" in n for n in app_go["neighbourDefs"])
    assert any(n.startswith("internal/app/util.go#ErrX") for n in app_go["neighbourDefs"])
    text = format_context([main_go])
    assert "neighbourDefs: " in text and "internal/app/app.go#App.Start (method)" in text


def test_context_go_neighbour_defs_caps(tmp_path):
    files = dict(GO_FILES)
    files["cmd/x.go"] = 'package main\n\nimport "github.com/x/y/internal/many"\n'
    for i in range(5):  # 5 x 40 > 200 total
        files[f"internal/p{i}/p.go"] = f"package p{i}\n\n" + "".join(
            f"func G{j:03d}() {{}}\n" for j in range(45))
        files["cmd/x.go"] += f'import "github.com/x/y/internal/p{i}"\n'
    kb, sha = _go_kb(tmp_path, files)
    one, many = file_context(kb, "demo", sha, ["internal/many/many.go"])[0], \
        file_context(kb, "demo", sha, ["cmd/x.go"])[0]
    big = [n for n in one["neighbourDefs"] if n.startswith("internal/many/big.go#")]
    assert len(big) == 40 and one["truncated"] is True  # per-file cap
    assert len(many["neighbourDefs"]) == 200 and many["truncated"] is True  # total cap
    # exported defs are the ones kept when capping
    assert all("#F" in n for n in big)


def test_context_non_go_neighbour_defs_use_resolved_imports():
    billing = file_context(EXAMPLE_KB, "fixture", SHA2, ["app/services/billing.py"])[0]
    assert billing["truncated"] is False
    assert billing["neighbourDefs"]
    assert all(n.startswith("app/models.py#") for n in billing["neighbourDefs"])
