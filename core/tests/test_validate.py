import json

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.schemas import validate
from readcode.validate_cmd import validate_study

runner = CliRunner()

SHA = "a" * 40
SHA2 = "b" * 40
H_MAIN, H_UTIL, H_OTHER = "1" * 64, "2" * 64, "3" * 64


def _file(path, blob, lines):
    return {"path": path, "blob": blob, "language": "python", "lines": lines,
            "bytes": lines * 10, "indexed": True}


def _explain(path, blob, summary="s", blocks=None):
    return {"schemaVersion": 1, "path": path, "blobHash": blob, "summary": summary,
            "blocks": blocks if blocks is not None else
            [{"id": "b1", "range": [1, 2], "title": "t", "body": "b"}]}


@pytest.fixture()
def mini(tmp_path):
    """Hand-built clean study with one snapshot. Returns (kb, study_dir, snap_dir)."""
    kb = tmp_path / "kb"
    sd = kb / "demo"
    kbio.atomic_write_json(sd / "study.json", {
        "schemaVersion": 1, "name": "demo", "title": "Demo", "repo": {"url": "x"},
        "language": "es", "exclude": [], "tools": {"graphify": False, "archify": True},
        "snapshots": [{"sha": SHA, "date": "2026-01-01T00:00:00Z", "message": "m",
                       "status": "explained"}]})
    snap = kbio.snapshot_dir(sd, SHA)
    kbio.atomic_write_json(snap / "tree.json", {
        "schemaVersion": 1, "sha": SHA, "excluded": [],
        "files": [_file("app/main.py", H_MAIN, 10), _file("app/util.py", H_UTIL, 8),
                  _file("app/other.py", H_OTHER, 3)]})
    kbio.atomic_write_json(snap / "symbols.json", {"schemaVersion": 1, "sha": SHA, "files": {
        "app/main.py": {"defs": [{"name": "main", "kind": "function", "range": [1, 5]},
                                 {"name": "helper", "kind": "function", "range": [6, 10]}],
                        "refs": [], "imports": []},
        "app/util.py": {"defs": [{"name": "helper", "kind": "function", "range": [1, 4]},
                                 {"name": "fmt", "kind": "function", "range": [5, 8]}],
                        "refs": [], "imports": []},
        "app/other.py": {"defs": [], "refs": [], "imports": []}}})
    kbio.atomic_write_json(kbio.explain_path(snap, "app/main.py"), _explain(
        "app/main.py", H_MAIN, "Usa [[ref:app/util.py#fmt]] y [[archify:arch]].",
        [{"id": "b1", "range": [1, 5], "title": "main", "body": "Ver [[ref:#helper]]."},
         {"id": "b2", "range": [6, 10], "title": "helper", "body": "`[[ref:nope#x]]`"}]))
    kbio.atomic_write_json(kbio.explain_path(snap, "app/util.py"), _explain("app/util.py", H_UTIL))
    kbio.atomic_write_json(kbio.explain_path(snap, "app/other.py"), _explain(
        "app/other.py", H_OTHER, "Ambigua: [[ref:#helper]]"))
    kbio.atomic_write_json(kbio.dir_summary_path(snap, ""), {
        "schemaVersion": 1, "path": "", "summary": "Raíz", "children": [
            {"path": "app", "kind": "dir", "oneLine": "código"}]})
    kbio.atomic_write_json(kbio.dir_summary_path(snap, "app"), {
        "schemaVersion": 1, "path": "app", "summary": "[[ref:app/main.py:L1-3]]", "children": []})
    kbio.atomic_write_json(snap / "tours" / "intro.json", {
        "schemaVersion": 1, "id": "intro", "title": "Intro", "description": "Empieza aquí",
        "steps": [{"path": "app/main.py", "range": [1, 5], "title": "s1",
                   "body": "La función [[ref:#main]]"}]})
    (snap / "overview.md").write_bytes(b"# Visi\xc3\xb3n\r\n\r\nVer [[ref:app/util.py#fmt|fmt]].\r\n")
    kbio.atomic_write_text(snap / "diagrams" / "arch.html", "<html></html>")
    return kb, sd, snap


def links(snap):
    return kbio.read_json(snap / "links.json")


def problems_text(problems):
    return "\n".join(f"{p['file']}: {p['problem']}" for p in problems)


def test_clean_study_exit0_and_links(mini):
    kb, sd, snap = mini
    r = runner.invoke(app, ["validate", str(kb), "demo"])
    assert r.exit_code == 0, r.output
    data = links(snap)
    assert validate("links", data) == []
    assert data["sha"] == SHA
    docs = data["docs"]
    assert set(docs) == {"explain/app/main.py.json", "explain/app/util.py.json",
                         "explain/app/other.py.json", "dirs/_root.json", "dirs/app.json",
                         "tours/intro.json", "tours/intro.json#1", "overview.md"}
    assert docs["explain/app/util.py.json"] == [] and docs["dirs/_root.json"] == []
    main = docs["explain/app/main.py.json"]
    assert main == [
        {"raw": "[[ref:app/util.py#fmt]]", "kind": "symbol", "status": "exact",
         "target": "app/util.py", "range": [5, 8]},
        {"raw": "[[archify:arch]]", "kind": "archify", "status": "exact",
         "target": "diagrams/arch.html"},
        {"raw": "[[ref:#helper]]", "kind": "symbol", "status": "exact",
         "target": "app/main.py", "range": [6, 10]},
    ]
    assert docs["explain/app/other.py.json"] == [
        {"raw": "[[ref:#helper]]", "kind": "symbol", "status": "ambiguous",
         "candidates": [{"target": "app/main.py", "range": [6, 10]},
                        {"target": "app/util.py", "range": [1, 4]}]}]
    assert docs["dirs/app.json"][0]["range"] == [1, 3]
    assert docs["tours/intro.json"] == []
    assert docs["tours/intro.json#1"][0]["target"] == "app/main.py"
    assert docs["overview.md"][0]["target"] == "app/util.py"
    assert kbio.read_json(snap / "issues.json") == {"schemaVersion": 1, "issues": []}


def test_json_output_empty_on_clean(mini):
    kb, _, _ = mini
    r = runner.invoke(app, ["validate", str(kb), "demo", "--sha", SHA[:8], "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == []


def _problems(kb, **kw):
    return validate_study(kb, "demo", **kw)


def test_stale_blobhash(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(kbio.explain_path(snap, "app/util.py"), _explain("app/util.py", "9" * 64))
    probs = _problems(kb)
    assert any(p["file"] == f"snapshots/{SHA}/explain/app/util.py.json"
               and "stale explanation" in p["problem"] for p in probs), problems_text(probs)


def test_overlapping_and_out_of_range_blocks(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(kbio.explain_path(snap, "app/main.py"), _explain(
        "app/main.py", H_MAIN, blocks=[
            {"id": "b1", "range": [1, 5], "title": "a", "body": ""},
            {"id": "b2", "range": [4, 9], "title": "b", "body": ""},
            {"id": "b2", "range": [10, 11], "title": "c", "body": ""}]))
    text = problems_text(_problems(kb))
    assert "overlap" in text
    assert "duplicate block id" in text
    assert "outside the file" in text


def test_broken_and_invalid_refs(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(kbio.dir_summary_path(snap, "app"), {
        "schemaVersion": 1, "path": "app", "children": [],
        "summary": "[[ref:app/main.py#nope]] [[ref:app/main.py:L1-99]] [[ref:app]]"})
    probs = _problems(kb)
    text = problems_text(probs)
    assert "broken reference [[ref:app/main.py#nope]]" in text
    assert "broken reference [[ref:app/main.py:L1-99]]" in text
    assert "invalid marker [[ref:app]]" in text
    # links.json is still written, with the broken entries
    entries = links(snap)["docs"]["dirs/app.json"]
    assert [e["status"] for e in entries] == ["broken", "broken", "broken"]
    assert entries[2]["kind"] == "invalid"
    issues = kbio.read_json(snap / "issues.json")["issues"]
    assert issues and all(i["source"] == "validate" for i in issues)
    assert {i["file"] for i in issues} == {"dirs/app.json"}


def test_missing_archify_diagram(mini):
    kb, _, snap = mini
    (snap / "diagrams" / "arch.html").unlink()
    (snap / "diagrams" / "arch.mmd").write_text("graph TD", encoding="utf-8")
    probs = _problems(kb)
    assert any("[[archify:arch]]" in p["problem"] and "diagrams/arch.html" in p["hint"]
               for p in probs), problems_text(probs)
    entry = links(snap)["docs"]["explain/app/main.py.json"][1]
    assert entry == {"raw": "[[archify:arch]]", "kind": "archify", "status": "broken",
                     "target": "diagrams/arch.html"}


def test_invalid_schema_and_cli_exit1(mini):
    kb, _, snap = mini
    doc = _explain("app/util.py", H_UTIL)
    del doc["summary"]
    kbio.atomic_write_json(kbio.explain_path(snap, "app/util.py"), doc)
    (snap / "tours" / "bad.json").write_text("{not json", encoding="utf-8")
    r = runner.invoke(app, ["validate", str(kb), "demo", "--json"])
    assert r.exit_code == 1
    out = json.loads(r.output)
    assert all(set(p) == {"file", "problem", "hint"} for p in out)
    files = {p["file"] for p in out}
    assert f"snapshots/{SHA}/explain/app/util.py.json" in files
    assert f"snapshots/{SHA}/tours/bad.json" in files
    r = runner.invoke(app, ["validate", str(kb), "demo"])
    assert r.exit_code == 1
    assert f"snapshots/{SHA}/explain/app/util.py.json: " in r.output


def test_path_mismatch_and_tour_range(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(kbio.explain_path(snap, "app/util.py"), _explain("app/main.py", H_MAIN))
    kbio.atomic_write_json(snap / "tours" / "intro.json", {
        "schemaVersion": 1, "id": "intro", "title": "Intro", "description": "",
        "steps": [{"path": "app/other.py", "range": [2, 7], "title": "s", "body": ""}]})
    text = problems_text(_problems(kb))
    assert "does not match its location" in text
    assert "tour step 1" in text


def test_issues_keep_other_sources(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(snap / "issues.json", {"schemaVersion": 1, "issues": [
        {"problem": "old", "source": "validate"},
        {"file": "x", "problem": "gen", "hint": "h", "source": "generator"}]})
    assert _problems(kb) == []
    assert kbio.read_json(snap / "issues.json")["issues"] == [
        {"file": "x", "problem": "gen", "hint": "h", "source": "generator"}]


def test_diff_validation_and_links(mini):
    kb, sd, snap = mini
    study = kbio.read_json(sd / "study.json")
    study["snapshots"].append({"sha": SHA2, "date": "2026-01-02T00:00:00Z", "message": "m2",
                               "status": "indexed"})
    kbio.atomic_write_json(sd / "study.json", study)
    snap2 = kbio.snapshot_dir(sd, SHA2)
    tree2 = kbio.read_json(snap / "tree.json")
    tree2["sha"] = SHA2
    tree2["files"] = [f for f in tree2["files"] if f["path"] != "app/util.py"]
    kbio.atomic_write_json(snap2 / "tree.json", tree2)
    ddir = sd / "diffs" / f"{SHA}..{SHA2}"
    kbio.atomic_write_json(ddir / "changes.json", {
        "schemaVersion": 1, "from": SHA, "to": SHA2, "files": [
            {"path": "app/util.py", "status": "deleted", "fromBlob": H_UTIL, "hunks": [
                {"fromRange": [1, 8], "toRange": None}]}]})
    kbio.atomic_write_text(ddir / "explain.md", "Se borra [[ref:app/util.py:L1-8]]\r\n")
    kbio.atomic_write_json(ddir / "explain" / "app/util.py.json", {
        "schemaVersion": 1, "path": "app/util.py", "summary": "[[ref:app/main.py:L1-2]]",
        "hunks": [{"index": 0, "body": "ok"}, {"index": 3, "body": "[[ref:app/x.py#y]]"}]})
    probs = _problems(kb)
    text = problems_text(probs)
    assert "hunk index 3" in text
    assert "broken reference [[ref:app/x.py#y]]" in text
    assert all(p["file"].startswith("diffs/") for p in probs), text
    dl = kbio.read_json(ddir / "links.json")
    assert validate("links", dl) == [] and dl["sha"] == SHA2
    assert set(dl["docs"]) == {"explain.md", "explain/app/util.py.json"}
    # deleted file: resolved against snapshot A as fallback
    assert dl["docs"]["explain.md"][0]["status"] == "exact"
    assert dl["docs"]["explain/app/util.py.json"][0]["target"] == "app/main.py"


def test_tour_steps_get_their_own_doc_keys(mini):
    """The same raw marker in two steps resolves relative to each step's file."""
    kb, _, snap = mini
    kbio.atomic_write_json(snap / "tours" / "intro.json", {
        "schemaVersion": 1, "id": "intro", "title": "Intro", "description": "Ver [[ref:#fmt]]",
        "steps": [
            {"path": "app/main.py", "range": [1, 5], "title": "s1", "body": "[[ref:#helper]]"},
            {"path": "app/util.py", "range": [1, 4], "title": "s2", "body": "[[ref:#helper]]"},
            {"path": "app/other.py", "range": [1, 3], "title": "s3", "body": "sin marcas"}]})
    assert _problems(kb) == []
    docs = links(snap)["docs"]
    assert docs["tours/intro.json"][0]["target"] == "app/util.py"
    assert docs["tours/intro.json#1"] == [
        {"raw": "[[ref:#helper]]", "kind": "symbol", "status": "exact",
         "target": "app/main.py", "range": [6, 10]}]
    assert docs["tours/intro.json#2"] == [
        {"raw": "[[ref:#helper]]", "kind": "symbol", "status": "exact",
         "target": "app/util.py", "range": [1, 4]}]
    assert docs["tours/intro.json#3"] == []


def test_same_raw_resolving_differently_in_one_doc_is_reported(mini):
    from readcode.validate_cmd import _Collector, _Resolver

    _, _, snap = mini
    tree = kbio.read_json(snap / "tree.json")
    symbols = kbio.read_json(snap / "symbols.json")
    res, out = _Resolver(tree, symbols, set()), _Collector()
    res.markdown("k.json", "x/k.json", "[[ref:#helper]]", "app/main.py", "a", out)
    res.markdown("k.json", "x/k.json", "[[ref:#helper]]", "app/main.py", "b", out)
    assert out.problems == []  # same resolution twice is fine
    res.markdown("k.json", "x/k.json", "[[ref:#helper]]", "app/util.py", "c", out)
    assert len(out.problems) == 1
    assert "resolves differently" in out.problems[0]["problem"]
    assert out.problems[0]["file"] == "x/k.json"


def test_search_json_lists_every_explain_block(mini):
    kb, _, snap = mini
    kbio.atomic_write_json(kbio.explain_path(snap, "app/broken.py"), {"schemaVersion": 1})
    _problems(kb)  # broken.py is reported and left out of the index
    data = kbio.read_json(snap / "search.json")
    assert validate("search", data) == []
    assert data == [
        {"path": "app/main.py", "blockId": "b1", "title": "main", "range": [1, 5]},
        {"path": "app/main.py", "blockId": "b2", "title": "helper", "range": [6, 10]},
        {"path": "app/other.py", "blockId": "b1", "title": "t", "range": [1, 2]},
        {"path": "app/util.py", "blockId": "b1", "title": "t", "range": [1, 2]},
    ]
