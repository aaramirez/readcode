import json
import shutil

import pytest
from typer.testing import CliRunner

from readcode import graph_cmd, kbio
from readcode.cli import app
from readcode.diff_cmd import DiffError, compute_hunks, diff_snapshots
from readcode.graph_cmd import graph_snapshot
from readcode.plan_cmd import _parents, plan_snapshot
from readcode.schemas import validate

runner = CliRunner()


@pytest.fixture()
def study(tmp_path, fixture_repo):
    repo, sha1, sha2 = fixture_repo
    for args in (["init", str(tmp_path), "demo", "--repo", str(repo)],
                 ["snapshot", str(tmp_path), "demo", "--sha", sha1],
                 ["snapshot", str(tmp_path), "demo", "--sha", sha2]):
        r = runner.invoke(app, args)
        assert r.exit_code == 0, r.output
    return tmp_path, tmp_path / "demo", sha1, sha2


def tree(sd, sha):
    return kbio.read_json(sd / "snapshots" / sha / "tree.json")


def fake_explain(sd, sha, only=None):
    snap = kbio.snapshot_dir(sd, sha)
    for f in tree(sd, sha)["files"]:
        if only and f["path"] not in only:
            continue
        doc = {"schemaVersion": 1, "path": f["path"], "blobHash": f["blob"], "summary": "x",
               "blocks": [{"id": "b1", "range": [1, 1], "title": "t", "body": "b"}]}
        assert validate("explain", doc) == []
        kbio.atomic_write_json(kbio.explain_path(snap, f["path"]), doc)


def fake_dirs(sd, sha):
    snap = kbio.snapshot_dir(sd, sha)
    for d in {x for f in tree(sd, sha)["files"] for x in _parents(f["path"])}:
        kbio.atomic_write_json(kbio.dir_summary_path(snap, d),
                               {"schemaVersion": 1, "path": d, "summary": "s", "children": []})


def test_path_helpers(tmp_path):
    assert kbio.explain_path(tmp_path, "app/main.py").as_posix().endswith("explain/app/main.py.json")
    assert kbio.dir_summary_path(tmp_path, "").name == "_root.json"
    assert kbio.dir_summary_path(tmp_path, "app/services").as_posix().endswith("dirs/app/services.json")


def test_plan_fresh_all_pending_and_batch_limit(study):
    _, sd, sha1, _ = study
    plan = plan_snapshot(sd.parent, "demo", sha1, batch_lines=15)
    explainable = {f["path"] for f in tree(sd, sha1)["files"]}
    got = [f["path"] for b in plan["batches"] for f in b["files"]]
    assert set(got) == explainable and len(got) == len(explainable)
    assert plan["reused"] == 0 and plan["overview"] and plan["tours"] and not plan["done"]
    assert len(plan["batches"]) > 1
    for b in plan["batches"]:
        total = sum(f["lines"] for f in b["files"])
        assert total <= 15 or len(b["files"]) == 1
    assert plan["batches"][0]["id"] == "batch-001"
    assert plan["dirs"][-1] == "" and set(plan["dirs"][:2]) == {"app/services", "web/src"}
    assert kbio.read_json(sd / "snapshots" / sha1 / "plan.json") == plan


def test_plan_reuse_and_pending(study):
    kb, sd, sha1, sha2 = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha2)
    plan = plan_snapshot(kb, "demo", sha2[:10])
    pending = {f["path"] for b in plan["batches"] for f in b["files"]}
    assert pending == {"app/services/billing.py", "app/services/refunds.py", "web/src/api.ts"}
    n_files = len(tree(sd, sha2)["files"])
    assert plan["reused"] == n_files - 3
    assert (sd / "snapshots" / sha2 / "explain" / "app" / "main.py.json").is_file()
    assert not (sd / "snapshots" / sha2 / "explain" / "app" / "services" / "billing.py.json").exists()
    assert plan["dirs"] == ["app/services", "web/src", "app", "web", ""]
    assert plan["overview"] and plan["tours"]


def test_plan_inherits_dirs_tours_diagrams(study):
    kb, sd, sha1, sha2 = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    s1 = kbio.snapshot_dir(sd, sha1)
    kbio.atomic_write_text(s1 / "overview.md", "# o\n")
    kbio.atomic_write_json(s1 / "tours" / "t.json", {"id": "t"})
    kbio.atomic_write_text(s1 / "diagrams" / "a.mmd", "graph TD\n")
    plan = plan_snapshot(kb, "demo", sha2)
    s2 = kbio.snapshot_dir(sd, sha2)
    all_dirs = {x for f in tree(sd, sha2)["files"] for x in _parents(f["path"])}
    affected = {"app/services", "app", "web/src", "web", "db", ""}
    assert set(plan["dirs"]) == affected
    assert plan["reusedDirs"] == len(all_dirs) - len(affected) > 0
    assert (s2 / "dirs" / "worker.json").is_file()
    assert not (s2 / "dirs" / "db.json").exists()
    assert plan["overview"] and not (s2 / "overview.md").exists()
    assert plan["tours"] is False and (s2 / "tours" / "t.json").is_file()
    assert (s2 / "diagrams" / "a.mmd").is_file()


def test_plan_same_tree_inherits_overview(study):
    kb, sd, sha1, _ = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    kbio.atomic_write_text(kbio.snapshot_dir(sd, sha1) / "overview.md", "# o\n")
    sha2 = study[3]
    snap2 = kbio.snapshot_dir(sd, sha2)
    kbio.atomic_write_json(snap2 / "tree.json", {**tree(sd, sha1), "sha": sha2})
    plan = plan_snapshot(kb, "demo", sha2)
    assert plan["overview"] is False and (snap2 / "overview.md").is_file()
    assert plan["batches"] == [] and plan["dirs"] == []


def test_plan_done(study):
    kb, sd, sha1, _ = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    snap = kbio.snapshot_dir(sd, sha1)
    kbio.atomic_write_text(snap / "overview.md", "# o\n")
    kbio.atomic_write_json(snap / "tours" / "t.json", {})
    plan = plan_snapshot(kb, "demo", sha1)
    assert plan == {"sha": sha1, "reusedFrom": None, "reused": 0, "reusedDirs": 0, "batches": [],
                    "dirs": [], "overview": False, "tours": False, "abandoned": [],
                    "abandonedDirs": [], "done": True}


def test_plan_after_reexplaining_keeps_affected_dirs_and_overview_pending(study):
    """Regression: once changed files are re-explained, re-running plan must not copy the
    previous snapshot's summaries of their ancestor dirs nor its overview."""
    kb, sd, sha1, sha2 = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    kbio.atomic_write_text(kbio.snapshot_dir(sd, sha1) / "overview.md", "# o\n")
    first = plan_snapshot(kb, "demo", sha2)
    assert first["reusedFrom"] == sha1
    affected = {"app/services", "app", "web/src", "web", "db", ""}
    assert set(first["dirs"]) == affected
    fake_explain(sd, sha2)  # the wave re-explains every changed file
    again = plan_snapshot(kb, "demo", sha2)
    s2 = kbio.snapshot_dir(sd, sha2)
    assert again["batches"] == []
    assert set(again["dirs"]) == affected
    assert not (s2 / "dirs" / "app" / "services.json").exists()
    assert not (s2 / "dirs" / "_root.json").exists()
    assert again["overview"] is True and not (s2 / "overview.md").exists()
    assert (s2 / "dirs" / "worker.json").is_file()


def test_plan_abandoned_files(study):
    kb, sd, sha1, _ = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    snap = kbio.snapshot_dir(sd, sha1)
    kbio.atomic_write_text(snap / "overview.md", "# o\n")
    kbio.atomic_write_json(snap / "tours" / "t.json", {})
    kbio.explain_path(snap, "app/models.py").unlink()
    kbio.atomic_write_json(snap / "issues.json", {"schemaVersion": 1, "issues": [
        {"file": "explain/app/models.py.json", "problem": "failed twice", "source": "generator"},
        {"file": "explain/app/main.py.json", "problem": "x", "source": "validate"}]})
    plan = plan_snapshot(kb, "demo", sha1)
    assert plan["batches"] == [] and plan["abandoned"] == ["app/models.py"]
    assert plan["dirs"] == [] and plan["overview"] is False and plan["done"] is True
    # removing the issue makes the file pending again (retry)
    kbio.atomic_write_json(snap / "issues.json", {"schemaVersion": 1, "issues": []})
    plan = plan_snapshot(kb, "demo", sha1)
    assert [f["path"] for b in plan["batches"] for f in b["files"]] == ["app/models.py"]
    assert plan["abandoned"] == [] and "app" in plan["dirs"] and plan["overview"] is True


def test_plan_abandoned_dirs_including_root(study):
    kb, sd, sha1, _ = study
    fake_explain(sd, sha1)
    fake_dirs(sd, sha1)
    snap = kbio.snapshot_dir(sd, sha1)
    kbio.atomic_write_text(snap / "overview.md", "# o\n")
    kbio.atomic_write_json(snap / "tours" / "t.json", {})
    kbio.dir_summary_path(snap, "").unlink()
    kbio.dir_summary_path(snap, "app/services").unlink()
    kbio.dir_summary_path(snap, "web").unlink()
    kbio.atomic_write_json(snap / "issues.json", {"schemaVersion": 1, "issues": [
        {"file": "dirs/_root.json", "problem": "failed twice", "source": "generator"},
        {"file": "dirs/app/services.json", "problem": "failed twice", "source": "generator"},
        {"file": "dirs/web.json", "problem": "x", "source": "validate"},
        {"file": "dirs/app.json", "problem": "summary exists", "source": "generator"}]})
    plan = plan_snapshot(kb, "demo", sha1)
    assert plan["dirs"] == ["web"]
    assert plan["abandonedDirs"] == ["", "app/services"]
    assert plan["abandoned"] == [] and plan["done"] is False
    assert "2 directorios abandonados" in runner.invoke(
        app, ["plan", str(kb), "demo", "--sha", sha1]).output
    fake_dirs(sd, sha1)  # once written, an abandoned dir is simply done
    plan = plan_snapshot(kb, "demo", sha1)
    assert plan["dirs"] == [] and plan["abandonedDirs"] == [] and plan["done"] is True


def test_plan_does_not_resurrect_deleted_tours_or_diagrams(study):
    kb, sd, sha1, sha2 = study
    fake_explain(sd, sha1)
    s1, s2 = kbio.snapshot_dir(sd, sha1), kbio.snapshot_dir(sd, sha2)
    kbio.atomic_write_json(s1 / "tours" / "a.json", {"id": "a"})
    kbio.atomic_write_json(s1 / "tours" / "b.json", {"id": "b"})
    kbio.atomic_write_text(s1 / "diagrams" / "x.html", "<html></html>")
    kbio.atomic_write_text(s1 / "diagrams" / "y.mmd", "graph TD\n")
    plan_snapshot(kb, "demo", sha2)
    assert sorted(p.name for p in (s2 / "tours").iterdir()) == ["a.json", "b.json"]
    (s2 / "tours" / "a.json").unlink()
    for f in (s2 / "diagrams").iterdir():
        f.unlink()  # diagrams/ left empty
    plan = plan_snapshot(kb, "demo", sha2)
    assert sorted(p.name for p in (s2 / "tours").iterdir()) == ["b.json"]
    assert list((s2 / "diagrams").iterdir()) == []
    assert plan["tours"] is False


def test_plan_stale_explain_hash_is_pending(study):
    kb, sd, sha1, _ = study
    fake_explain(sd, sha1)
    p = kbio.explain_path(kbio.snapshot_dir(sd, sha1), "app/models.py")
    doc = kbio.read_json(p)
    doc["blobHash"] = "0" * 64
    kbio.atomic_write_json(p, doc)
    plan = plan_snapshot(kb, "demo", sha1)
    assert [f["path"] for b in plan["batches"] for f in b["files"]] == ["app/models.py"]


def test_plan_cli_json_and_errors(study):
    kb, _, sha1, _ = study
    r = runner.invoke(app, ["plan", str(kb), "demo", "--sha", sha1, "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["sha"] == sha1
    r = runner.invoke(app, ["plan", str(kb), "demo", "--sha", sha1[:8]])
    assert r.exit_code == 0 and "Plan" in r.output
    r = runner.invoke(app, ["plan", str(kb), "demo", "--sha", "deadbeef"])
    assert r.exit_code == 1


# ----------------------------------------------------------------- diff


def test_diff_fixture(study):
    kb, sd, sha1, sha2 = study
    r = runner.invoke(app, ["diff", str(kb), "demo", sha1[:8], sha2[:8]])
    assert r.exit_code == 0, r.output
    path = sd / "diffs" / f"{sha1}..{sha2}" / "changes.json"
    doc = kbio.read_json(path)
    assert validate("changes", doc) == []
    by = {f["path"]: f for f in doc["files"]}
    assert by["app/services/billing.py"]["status"] == "modified"
    assert by["app/services/billing.py"]["hunks"] and by["app/services/billing.py"]["hunks"][0]["fromRange"] is None
    assert by["app/services/refunds.py"]["status"] == "added"
    assert by["db/queries.sql"]["status"] == "deleted"
    assert by["web/src/api.ts"]["status"] == "modified"


def test_diff_rename_and_unknown_sha(study):
    kb, sd, sha1, sha2 = study
    t = tree(sd, sha2)
    moved = next(f for f in t["files"] if f["path"] == "app/models.py")
    t["files"] = [f for f in t["files"] if f["path"] != "app/models.py"]
    t["files"].append({**moved, "path": "app/entities.py"})
    kbio.atomic_write_json(sd / "snapshots" / sha2 / "tree.json", t)
    doc = diff_snapshots(kb, "demo", sha1, sha2)
    ren = next(f for f in doc["files"] if f["status"] == "renamed")
    assert ren["path"] == "app/entities.py" and ren["oldPath"] == "app/models.py"
    assert not any(f["path"] == "app/models.py" for f in doc["files"])
    with pytest.raises(DiffError):
        diff_snapshots(kb, "demo", sha1, "abcdef")


def test_compute_hunks_ranges_and_merge():
    old = [f"l{i}\n" for i in range(1, 11)]
    new = list(old)
    new[1] = "X\n"            # line 2 changed
    new[3] = "Y\n"            # line 4 changed (gap of 1 line -> merged)
    new.append("tail\n")      # pure insert at end
    hunks = compute_hunks(old, new)
    assert hunks[0]["fromRange"] == [2, 4] and hunks[0]["toRange"] == [2, 4]
    assert hunks[1] == {"fromRange": None, "toRange": [11, 11], "header": "@@ -11,0 +11,1 @@"}
    assert compute_hunks(old, old[:5]) == [{"fromRange": [6, 10], "toRange": None, "header": "@@ -6,5 +6,0 @@"}]


# ----------------------------------------------------------------- graph


def test_graph_with_fake_runner(study, monkeypatch):
    kb, sd, sha1, _ = study
    seen = {}

    def fake(exe, directory):
        seen["files"] = sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())
        out = directory / "graphify-out"
        out.mkdir()
        (out / "graph.json").write_text('{"nodes": []}', encoding="utf-8")
        (out / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")

    monkeypatch.setattr(graph_cmd.shutil, "which", lambda name: "/fake/graphify")
    monkeypatch.setattr(graph_cmd, "run_graphify", fake)
    r = runner.invoke(app, ["graph", str(kb), "demo", "--sha", sha1])
    assert r.exit_code == 0, r.output
    assert "app/main.py" in seen["files"] and not any(p.startswith("node_modules") for p in seen["files"])
    g = sd / "snapshots" / sha1 / "graph"
    assert json.loads((g / "graph.json").read_text()) == {"nodes": []}
    assert (g / "GRAPH_REPORT.md").is_file()
    assert kbio.read_json(sd / "study.json")["tools"]["graphify"] is True


def test_graph_not_installed(study, monkeypatch, capsys):
    kb, sd, sha1, _ = study
    monkeypatch.setattr(graph_cmd.shutil, "which", lambda name: None)
    assert graph_snapshot(kb, "demo", sha1) is False
    assert "graphify" in capsys.readouterr().err
    assert kbio.read_json(sd / "study.json")["tools"]["graphify"] is False
    r = runner.invoke(app, ["graph", str(kb), "demo", "--sha", sha1])
    assert r.exit_code == 0


def test_graph_failure_is_soft(study, monkeypatch, capsys):
    kb, sd, sha1, _ = study

    def boom(exe, directory):
        raise graph_cmd.GraphError("kaput")

    monkeypatch.setattr(graph_cmd.shutil, "which", lambda name: "/fake/graphify")
    monkeypatch.setattr(graph_cmd, "run_graphify", boom)
    assert graph_snapshot(kb, "demo", sha1) is False
    assert "kaput" in capsys.readouterr().err
    assert kbio.read_json(sd / "study.json")["tools"]["graphify"] is False


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("graphify") is None, reason="graphify not installed")
def test_graph_real_graphify(study):
    kb, sd, sha1, _ = study
    assert graph_snapshot(kb, "demo", sha1) is True
    graph = sd / "snapshots" / sha1 / "graph" / "graph.json"
    assert isinstance(json.loads(graph.read_text(encoding="utf-8")), dict)
    assert kbio.read_json(sd / "study.json")["tools"]["graphify"] is True


def _odd_study(tmp_path, old: bytes, new: bytes, path="m.py"):
    """Hand-built study with two snapshots of one file (no git needed)."""
    from readcode.snapshot import count_lines

    kb, sd = tmp_path / "kb", tmp_path / "kb" / "demo"
    a, b = "a" * 40, "b" * 40
    kbio.atomic_write_json(sd / "study.json", {
        "schemaVersion": 1, "name": "demo", "title": "D", "repo": {"url": "x"},
        "language": "es", "exclude": [], "tools": {"graphify": False, "archify": False},
        "snapshots": [{"sha": a, "date": "2026-01-01T00:00:00Z", "message": "1", "status": "indexed"},
                      {"sha": b, "date": "2026-01-02T00:00:00Z", "message": "2", "status": "indexed"}]})
    for sha, data in ((a, old), (b, new)):
        h = kbio.sha256_hex(data)
        kbio.atomic_write_bytes(kbio.blob_path(sd, h), data)
        kbio.atomic_write_json(kbio.snapshot_dir(sd, sha) / "tree.json", {
            "schemaVersion": 1, "sha": sha, "excluded": [], "files": [
                {"path": path, "blob": h, "language": "python", "lines": count_lines(data),
                 "bytes": len(data), "indexed": True}]})
    return kb, sd, a, b


def test_diff_eol_only_change(tmp_path):
    kb, _, a, b = _odd_study(tmp_path, b"a = 1\r\nb = 2\r\n", b"a = 1\nb = 2\n")
    doc = diff_snapshots(kb, "demo", a, b)
    (f,) = doc["files"]
    assert f["status"] == "modified" and f["hunks"] == [] and f["eolOnly"] is True


def test_diff_eol_with_real_change_is_not_eol_only(tmp_path):
    kb, _, a, b = _odd_study(tmp_path, b"a = 1\r\nb = 2\r\n", b"a = 1\nb = 3\n")
    (f,) = diff_snapshots(kb, "demo", a, b)["files"]
    assert "eolOnly" not in f and len(f["hunks"]) == 1


def test_diff_hunks_use_newline_only_lines(tmp_path):
    old = "a\fb\nc\x85d\ne\u2028f\ng\rh\nkeep\nold\n".encode("utf-8")
    new = "a\fb\nc\x85d\ne\u2028f\ng\rh\nkeep\nnew\n".encode("utf-8")
    kb, _, a, b = _odd_study(tmp_path, old, new)
    doc = diff_snapshots(kb, "demo", a, b)
    (f,) = doc["files"]
    # "old" is line 6 when splitting only on "\n" (splitlines() would say 9)
    assert f["hunks"] == [{"fromRange": [6, 6], "toRange": [6, 6], "header": "@@ -6,1 +6,1 @@"}]
    assert f["hunks"] == compute_hunks(old.decode().split("\n")[:-1], new.decode().split("\n")[:-1])
