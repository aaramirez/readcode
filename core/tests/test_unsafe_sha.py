"""Central snapshot-sha safety: kbio.safe_snapshot_dir / resolve_sha and the commands that use them."""

import json
import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.plan_cmd import plan_snapshot

runner = CliRunner()
SHA = "a" * 40


def _link_dir(link, target):
    """Directory symlink, or a junction on Windows; skip the test when neither can be created."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError, AttributeError):
        pass
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode == 0:
            return
    pytest.skip("no se pueden crear enlaces simbólicos ni junctions")


def _study_json(sdir, snapshots):
    (sdir).mkdir(parents=True, exist_ok=True)
    (sdir / "study.json").write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")


def test_safe_snapshot_dir_accepts_40_hex(tmp_path):
    (tmp_path / "snapshots" / SHA).mkdir(parents=True)
    assert kbio.safe_snapshot_dir(tmp_path, SHA) == tmp_path / "snapshots" / SHA


@pytest.mark.parametrize("bad", ["../x", "a" * 39, "A" * 40, "", "a" * 40 + "/..", "/etc/passwd"])
def test_safe_snapshot_dir_rejects_bad_format(tmp_path, bad):
    with pytest.raises(kbio.UnsafeSnapshotError):
        kbio.safe_snapshot_dir(tmp_path, bad)


def test_safe_snapshot_dir_rejects_link_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "study" / "snapshots").mkdir(parents=True)
    _link_dir(tmp_path / "study" / "snapshots" / SHA, outside)
    with pytest.raises(kbio.UnsafeSnapshotError):
        kbio.safe_snapshot_dir(tmp_path / "study", SHA)


def test_resolve_sha_ignores_non_hex_entries():
    data = {"snapshots": [{"sha": "../evil"}, {"sha": "/abs/path"}, {"sha": SHA}]}
    assert kbio.resolve_sha(data, "a" * 8) == SHA
    with pytest.raises(ValueError):
        kbio.resolve_sha(data, "../evil")
    with pytest.raises(ValueError):
        kbio.resolve_sha(data, "/abs")


def test_resolve_sha_with_sdir_rejects_link_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sdir = tmp_path / "study"
    (sdir / "snapshots").mkdir(parents=True)
    _link_dir(sdir / "snapshots" / SHA, outside)
    with pytest.raises(kbio.UnsafeSnapshotError):
        kbio.resolve_sha({"snapshots": [{"sha": SHA}]}, SHA[:8], sdir)


def test_plan_ignores_absolute_and_traversal_shas(tmp_path):
    victim = tmp_path / "victim"
    (victim / "explain").mkdir(parents=True)
    (victim / "explain" / "a.py.json").write_text('{"blobHash": "h"}', encoding="utf-8")
    (victim / "overview.md").write_text("secret", encoding="utf-8")
    (victim / "tours").mkdir()
    (victim / "tours" / "t.md").write_text("secret", encoding="utf-8")
    kb = tmp_path / "kb"
    sdir = kb / "demo"
    snap = sdir / "snapshots" / SHA
    snap.mkdir(parents=True)
    kbio.atomic_write_json(snap / "tree.json", {"schemaVersion": 1, "sha": SHA, "excluded": [], "files": [
        {"path": "a.py", "blob": "h", "language": "python", "lines": 1, "bytes": 1, "indexed": False}]})
    _study_json(sdir, [
        {"sha": SHA, "date": "2026-02-01T00:00:00Z"},
        {"sha": str(victim), "date": "2026-01-01T00:00:00Z"},
        {"sha": "../../victim", "date": "2026-01-02T00:00:00Z"}])
    plan = plan_snapshot(kb, "demo", SHA)
    assert plan["reusedFrom"] is None and plan["reused"] == 0 and plan["reusedDirs"] == 0
    assert not (snap / "explain").exists() and not (snap / "overview.md").exists()
    assert not (snap / "tours").exists()
    assert sorted(p.name for p in victim.iterdir()) == ["explain", "overview.md", "tours"]


def test_plan_ignores_linked_snapshot_pointing_outside(tmp_path):
    victim = tmp_path / "victim"
    (victim / "explain").mkdir(parents=True)
    (victim / "explain" / "a.py.json").write_text('{"blobHash": "h"}', encoding="utf-8")
    kb = tmp_path / "kb"
    sdir = kb / "demo"
    snap = sdir / "snapshots" / SHA
    snap.mkdir(parents=True)
    kbio.atomic_write_json(snap / "tree.json", {"schemaVersion": 1, "sha": SHA, "excluded": [], "files": [
        {"path": "a.py", "blob": "h", "language": "python", "lines": 1, "bytes": 1, "indexed": False}]})
    other = "b" * 40
    _link_dir(sdir / "snapshots" / other, victim)
    _study_json(sdir, [{"sha": SHA, "date": "2026-02-01T00:00:00Z"},
                       {"sha": other, "date": "2026-01-01T00:00:00Z"}])
    plan = plan_snapshot(kb, "demo", SHA)
    assert plan["reusedFrom"] is None and plan["reused"] == 0
    assert not (snap / "explain").exists()


def test_archify_exits_2_on_linked_snapshot(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sdir = tmp_path / "kb" / "demo"
    (sdir / "snapshots").mkdir(parents=True)
    _link_dir(sdir / "snapshots" / SHA, outside)
    _study_json(sdir, [{"sha": SHA, "date": "2026-02-01T00:00:00Z"}])
    src = tmp_path / "in.json"
    src.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["archify", str(tmp_path / "kb"), "demo", SHA, "x", "architecture", str(src)])
    assert result.exit_code == 2
    assert "snapshot" in result.output
    assert not (outside / "diagrams").exists()


def test_cli_context_rejects_linked_snapshot(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sdir = tmp_path / "kb" / "demo"
    (sdir / "snapshots").mkdir(parents=True)
    _link_dir(sdir / "snapshots" / SHA, outside)
    _study_json(sdir, [{"sha": SHA, "date": "2026-02-01T00:00:00Z"}])
    result = runner.invoke(app, ["context", str(tmp_path / "kb"), "demo", "a.py", "--sha", SHA])
    assert result.exit_code != 0 and "resuelve fuera" in result.output
