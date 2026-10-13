"""``readcode archify`` (fake ARCHIFY_BIN) and ``readcode grammars`` (download mocked)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from readcode import archify_cmd, grammars_cmd, indexer
from readcode.cli import app

runner = CliRunner()
SHA = "a" * 40

FAKE_OK = """import { writeFileSync } from 'node:fs';
const argv = process.argv.slice(2);
const [cmd, type, input, out] = argv;
if (cmd !== 'finalize' || !argv.includes('--out-dir')) process.exit(3);
writeFileSync(out, `<html><body>${type}</body></html>`);
const od = argv[argv.indexOf('--out-dir') + 1];
writeFileSync(od + '/receipt.json', JSON.stringify(argv));
writeFileSync(process.env.ARGV_LOG || od + '/argv.log', JSON.stringify(argv));
"""
FAKE_FAIL = """import { writeFileSync } from 'node:fs';
writeFileSync(process.argv[5], '<html>partial');
console.error('boom');
process.exit(1);
"""


@pytest.fixture
def study(tmp_path):
    sdir = tmp_path / "kb" / "demo"
    (sdir / "snapshots" / SHA).mkdir(parents=True)
    (sdir / "study.json").write_text("{}", encoding="utf-8")
    src = tmp_path / "in.json"
    src.write_text('{"meta": {}}', encoding="utf-8")
    return tmp_path / "kb", sdir / "snapshots" / SHA / "diagrams", src


def _fake(tmp_path, monkeypatch, body):
    f = tmp_path / "archify.mjs"
    f.write_text(body, encoding="utf-8")
    monkeypatch.setenv("ARCHIFY_BIN", str(f))


def _args(kb, src, name="arquitectura", sha=SHA):
    return ["archify", str(kb), "demo", sha, name, "architecture", str(src)]


def test_archify_renders_and_copies_source(study, tmp_path, monkeypatch):
    if not shutil.which("node"):
        pytest.skip("node no está en el PATH")
    kb, diagrams, src = study
    _fake(tmp_path, monkeypatch, FAKE_OK)
    log = tmp_path / "argv.json"
    monkeypatch.setenv("ARGV_LOG", str(log))
    result = runner.invoke(app, _args(kb, src, sha=SHA[:8]) + ["--repo-root", str(tmp_path), "--quality", "showcase"])
    assert result.exit_code == 0, result.output
    argv = json.loads(log.read_text(encoding="utf-8"))
    assert argv[0] == "finalize" and "--out-dir" in argv
    out_dir = argv[argv.index("--out-dir") + 1]
    assert Path(out_dir).parent != diagrams and not Path(out_dir).exists()  # temp dir outside kb, removed
    assert argv[argv.index("--repo-root") + 1] == str(tmp_path) and "showcase" in argv
    assert (diagrams / "arquitectura.html").read_text(encoding="utf-8") == "<html><body>architecture</body></html>"
    assert json.loads((diagrams / "arquitectura.json").read_text(encoding="utf-8")) == {"meta": {}}
    assert [p.name for p in diagrams.iterdir()] == ["arquitectura.html", "arquitectura.json"]


def test_archify_bin_may_be_a_directory(study, tmp_path, monkeypatch):
    if not shutil.which("node"):
        pytest.skip("node no está en el PATH")
    kb, diagrams, src = study
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "archify.mjs").write_text(FAKE_OK, encoding="utf-8")
    monkeypatch.setenv("ARCHIFY_BIN", str(tmp_path))
    monkeypatch.setenv("ARGV_LOG", str(tmp_path / "log.json"))
    assert runner.invoke(app, _args(kb, src)).exit_code == 0
    assert (diagrams / "arquitectura.html").is_file()


def test_archify_failed_render_leaves_nothing(study, tmp_path, monkeypatch):
    if not shutil.which("node"):
        pytest.skip("node no está en el PATH")
    kb, diagrams, src = study
    _fake(tmp_path, monkeypatch, FAKE_FAIL)
    result = runner.invoke(app, _args(kb, src))
    assert result.exit_code == 2
    assert "boom" in result.output
    assert list(diagrams.iterdir()) == []


def test_archify_missing_archify_exits_2(study, tmp_path, monkeypatch):
    if not shutil.which("node"):
        pytest.skip("node no está en el PATH")
    kb, _, src = study
    monkeypatch.setenv("ARCHIFY_BIN", str(tmp_path / "nope.mjs"))
    result = runner.invoke(app, _args(kb, src))
    assert result.exit_code == 2
    assert "archify.mjs" in result.output


def test_archify_missing_node_exits_2(study, tmp_path, monkeypatch):
    kb, _, src = study
    _fake(tmp_path, monkeypatch, FAKE_OK)
    monkeypatch.setattr(archify_cmd.shutil, "which", lambda name: None)
    result = runner.invoke(app, _args(kb, src))
    assert result.exit_code == 2
    assert "node" in result.output


@pytest.mark.parametrize("name", ["../x", "a..b", "a/b", "", "a b"])
def test_archify_rejects_bad_names(study, name):
    kb, _, src = study
    result = runner.invoke(app, _args(kb, src, name=name))
    assert result.exit_code == 2
    assert "inválido" in result.output


def test_archify_missing_study_or_snapshot_exits_2(study):
    kb, _, src = study
    result = runner.invoke(app, ["archify", str(kb), "otro", SHA, "x", "architecture", str(src)])
    assert result.exit_code == 2 and "estudio" in result.output
    result = runner.invoke(app, ["archify", str(kb), "demo", "b" * 40, "x", "architecture", str(src)])
    assert result.exit_code == 2 and "snapshot" in result.output


# ------------------------------------------------------------------ grammars


def test_grammars_lists_used_languages_with_cache_state(monkeypatch):
    monkeypatch.setattr(grammars_cmd, "cached_grammars", lambda: {"python"})
    result = runner.invoke(app, ["grammars"])
    assert result.exit_code == 0
    rows = dict(line.split("\t") for line in result.output.strip().splitlines())
    assert rows["python"] == "en caché"
    assert rows["bash"].startswith("falta")
    assert "markdown" not in rows  # NOT_INDEXED languages need no grammar
    assert set(rows) == set(grammars_cmd.used_grammars())


def test_grammars_fetch_downloads_requested(monkeypatch):
    import tree_sitter_language_pack as tslp

    cache = {"python"}
    calls = []

    def fake_download(names):
        calls.append(list(names))
        cache.update(names)
        return len(names)

    monkeypatch.setattr(tslp, "download", fake_download)
    monkeypatch.setattr(grammars_cmd, "cached_grammars", lambda: set(cache))
    result = runner.invoke(app, ["grammars", "--fetch", "go", "rust"])
    assert result.exit_code == 0, result.output
    assert calls == [["go", "rust"]]
    result = runner.invoke(app, ["grammars", "--fetch"])
    assert result.exit_code == 0
    assert calls[1] == grammars_cmd.used_grammars()


def test_grammars_fetch_failure_and_unknown(monkeypatch):
    import tree_sitter_language_pack as tslp

    def boom(names):
        raise OSError("sin red")

    monkeypatch.setattr(tslp, "download", boom)
    result = runner.invoke(app, ["grammars", "--fetch", "go"])
    assert result.exit_code == 1 and "sin red" in result.output
    result = runner.invoke(app, ["grammars", "klingon"])
    assert result.exit_code == 1 and "desconocida" in result.output


def test_index_hints_grammars_fetch_on_load_failure(tmp_path, fixture_repo, monkeypatch):
    import tree_sitter_language_pack as tslp

    repo, sha1, _ = fixture_repo
    for args in (["init", str(tmp_path), "demo", "--repo", str(repo)],
                 ["snapshot", str(tmp_path), "demo", "--sha", sha1]):
        assert runner.invoke(app, args).exit_code == 0

    def offline(name):
        raise OSError("offline")

    monkeypatch.setattr(tslp, "get_language", offline)
    monkeypatch.setattr(indexer, "LOAD_FAILURES", set())
    indexer._load.cache_clear()
    try:
        result = runner.invoke(app, ["index", str(tmp_path), "demo", "--sha", sha1])
    finally:
        indexer._load.cache_clear()
    assert result.exit_code == 0
    assert "readcode grammars --fetch" in result.output
