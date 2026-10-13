"""The root directory summary lives at snapshots/<sha>/dir-root.json (v1: dirs/_root.json)."""

from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.validate_cmd import validate_study

runner = CliRunner()
SHA = "a" * 40


def _dir_doc(path, summary):
    return {"schemaVersion": 1, "path": path, "summary": summary, "children": []}


def _kb(tmp_path, dirs):
    """Study with one snapshot whose tree is ``dirs`` (a dir with one file each, plus a root file)."""
    kb = tmp_path / "kb"
    sd = kb / "demo"
    kbio.atomic_write_json(sd / "study.json", {
        "schemaVersion": 1, "name": "demo", "title": "Demo", "repo": {"url": "x"},
        "language": "es", "exclude": [], "tools": {"graphify": False, "archify": False},
        "snapshots": [{"sha": SHA, "date": "2026-01-01T00:00:00Z", "message": "m", "status": "explained"}]})
    snap = kbio.snapshot_dir(sd, SHA)
    paths = ["README.md"] + [f"{d}/a.py" for d in dirs]
    kbio.atomic_write_json(snap / "tree.json", {"schemaVersion": 1, "sha": SHA, "excluded": [], "files": [
        {"path": p, "blob": "1" * 64, "language": None, "lines": 1, "bytes": 1, "indexed": False}
        for p in paths]})
    for p in paths:
        kbio.atomic_write_json(kbio.explain_path(snap, p), {
            "schemaVersion": 1, "path": p, "blobHash": "1" * 64, "summary": "s",
            "blocks": [{"id": "b1", "range": [1, 1], "title": "t", "body": "b"}]})
    return kb, sd, snap


def test_root_summary_is_outside_dirs(tmp_path):
    assert kbio.dir_summary_path(tmp_path, "") == tmp_path / "dir-root.json"
    assert kbio.dir_summary_path(tmp_path, "_root") == tmp_path / "dirs" / "_root.json"


def test_repo_with_root_folder_has_two_distinct_summaries(tmp_path):
    kb, _, snap = _kb(tmp_path, ["_root"])
    kbio.atomic_write_json(kbio.dir_summary_path(snap, ""), _dir_doc("", "la raíz"))
    kbio.atomic_write_json(kbio.dir_summary_path(snap, "_root"), _dir_doc("_root", "la carpeta"))
    assert kbio.read_json(kbio.find_dir_summary(snap, ""))["summary"] == "la raíz"
    assert kbio.read_json(kbio.find_dir_summary(snap, "_root"))["summary"] == "la carpeta"
    assert validate_study(kb, "demo") == []
    docs = kbio.read_json(snap / "links.json")["docs"]
    assert {"dir-root.json", "dirs/_root.json"} <= set(docs)


def test_folder_named_root_is_not_a_legacy_root(tmp_path):
    kb, sd, snap = _kb(tmp_path, ["_root"])
    kbio.atomic_write_json(snap / "dirs" / "_root.json", _dir_doc("_root", "la carpeta"))
    assert kbio.legacy_root_path(snap) is None
    assert kbio.find_dir_summary(snap, "") is None
    problems = validate_study(kb, "demo")
    assert not any(p.get("code") == "legacy-root" for p in problems)
    from readcode.migrate_cmd import migrate_study
    assert migrate_study(kb, "demo") == []
    assert (snap / "dirs" / "_root.json").is_file() and not (snap / "dir-root.json").exists()


def test_v1_kb_warns_then_migrate_cleans(tmp_path):
    kb, sd, snap = _kb(tmp_path, ["app"])
    kbio.atomic_write_json(snap / "dirs" / "_root.json", _dir_doc("", "raíz v1"))
    kbio.atomic_write_json(kbio.dir_summary_path(snap, "app"), _dir_doc("app", "app"))
    problems = validate_study(kb, "demo")
    assert [p["code"] for p in problems] == ["legacy-root"]
    assert "dirs/_root.json" in kbio.read_json(snap / "links.json")["docs"]
    issues = kbio.read_json(snap / "issues.json")["issues"]
    assert issues[0]["code"] == "legacy-root"
    r = runner.invoke(app, ["validate", str(kb), "demo"])
    assert r.exit_code == 0 and "aviso:" in r.output  # a warning does not fail

    r = runner.invoke(app, ["migrate", str(kb)])  # all studies
    assert r.exit_code == 0, r.output
    assert "dirs/_root.json -> dir-root.json" in r.output and "readcode validate" in r.output
    assert not (snap / "dirs" / "_root.json").exists()
    assert kbio.read_json(snap / "dir-root.json")["summary"] == "raíz v1"

    assert validate_study(kb, "demo") == []
    assert "dir-root.json" in kbio.read_json(snap / "links.json")["docs"]
    again = runner.invoke(app, ["migrate", str(kb), "demo"])  # idempotent
    assert again.exit_code == 0 and "Nada que migrar" in again.output


def test_migrate_keeps_existing_dir_root(tmp_path):
    kb, _, snap = _kb(tmp_path, [])
    kbio.atomic_write_json(snap / "dirs" / "_root.json", _dir_doc("", "viejo"))
    kbio.atomic_write_json(snap / "dir-root.json", _dir_doc("", "nuevo"))
    assert validate_study(kb, "demo")[0]["code"] == "legacy-root"
    assert runner.invoke(app, ["migrate", str(kb), "demo"]).exit_code == 0
    assert kbio.read_json(snap / "dir-root.json")["summary"] == "nuevo"
    assert not (snap / "dirs" / "_root.json").exists()


def test_migrate_unknown_study_fails(tmp_path):
    r = runner.invoke(app, ["migrate", str(tmp_path), "nope"])
    assert r.exit_code == 1 and "error:" in r.output


def test_plan_inherits_legacy_root_under_new_name(tmp_path):
    from readcode.plan_cmd import plan_snapshot
    kb, sd, snap1 = _kb(tmp_path, [])
    sha2 = "b" * 40
    study = kbio.read_json(sd / "study.json")
    study["snapshots"].append({"sha": sha2, "date": "2026-01-02T00:00:00Z", "message": "m2", "status": "indexed"})
    kbio.atomic_write_json(sd / "study.json", study)
    snap2 = kbio.snapshot_dir(sd, sha2)
    kbio.atomic_write_bytes(snap2 / "tree.json", (snap1 / "tree.json").read_bytes())
    kbio.atomic_write_json(snap1 / "dirs" / "_root.json", _dir_doc("", "raíz v1"))
    kbio.atomic_write_text(snap1 / "overview.md", "# o\n")
    plan = plan_snapshot(kb, "demo", sha2)
    assert plan["reusedFrom"] == SHA and plan["dirs"] == []
    assert kbio.read_json(snap2 / "dir-root.json")["summary"] == "raíz v1"
    assert not (snap2 / "dirs" / "_root.json").exists()
