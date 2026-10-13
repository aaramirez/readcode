import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.schemas import validate

runner = CliRunner()


def _run(*args):
    r = runner.invoke(app, list(args))
    assert r.exit_code == 0, r.output
    return r


@pytest.fixture(scope="module")
def indexed(tmp_path_factory, fixture_repo):
    """Snapshot + index both fixture commits once. Returns (study_dir, sha1, sha2)."""
    repo, sha1, sha2 = fixture_repo
    kb = tmp_path_factory.mktemp("kb")
    _run("init", str(kb), "demo", "--repo", str(repo))
    for sha in (sha1, sha2):
        _run("snapshot", str(kb), "demo", "--sha", sha)
        _run("index", str(kb), "demo", "--sha", sha)
    return kb, kb / "demo", sha1, sha2


def symbols(sd, sha):
    return kbio.read_json(sd / "snapshots" / sha / "symbols.json")


def tree(sd, sha):
    return {f["path"]: f for f in kbio.read_json(sd / "snapshots" / sha / "tree.json")["files"]}


def defs_of(sym, path):
    return {(d["name"], d["kind"]): d for d in sym["files"][path]["defs"]}


def ref_names(sym, path):
    return {r["name"] for r in sym["files"][path]["refs"]}


def test_outputs_are_valid(indexed):
    _, sd, sha1, sha2 = indexed
    for sha in (sha1, sha2):
        sym = symbols(sd, sha)
        assert validate("symbols", sym) == []
        assert sym["sha"] == sha
        assert validate("tree", kbio.read_json(sd / "snapshots" / sha / "tree.json")) == []


def test_python_defs(indexed):
    _, sd, sha1, _ = indexed
    sym = symbols(sd, sha1)
    models = defs_of(sym, "app/models.py")
    assert models[("Invoice", "class")]["range"] == [1, 7]
    assert "parent" not in models[("Invoice", "class")]
    init = models[("__init__", "method")]
    assert init["parent"] == "Invoice" and init["range"] == [2, 4]
    assert models[("describe", "method")]["parent"] == "Invoice"

    billing = defs_of(sym, "app/services/billing.py")
    assert billing[("compute_total", "function")]["range"] == [4, 5]
    assert "parent" not in billing[("process", "function")]


def test_both_process_defs_present(indexed):
    _, sd, sha1, _ = indexed
    sym = symbols(sd, sha1)
    assert ("process", "function") in defs_of(sym, "app/services/billing.py")
    assert ("process", "function") in defs_of(sym, "app/services/auth.py")


def test_python_refs_and_imports(indexed):
    _, sd, sha1, sha2 = indexed
    sym = symbols(sd, sha1)
    main = sym["files"]["app/main.py"]
    assert {"process", "main", "print"} <= ref_names(sym, "app/main.py")
    resolved = {i["resolved"] for i in main["imports"]}
    assert {"app/services/billing.py", "app/services/auth.py"} <= resolved
    billing = sym["files"]["app/services/billing.py"]
    assert billing["imports"] == [{"module": "app.models", "line": 1, "resolved": "app/models.py"}]
    assert "Invoice" in ref_names(sym, "app/services/billing.py")
    # a def's own name is not a ref
    assert all(r["line"] != 8 or r["name"] != "process" for r in billing["refs"])

    sym2 = symbols(sd, sha2)
    refunds = sym2["files"]["app/services/refunds.py"]["imports"]
    assert refunds == [
        {"module": "app.services.billing", "line": 1, "resolved": "app/services/billing.py"}
    ]


def test_typescript(indexed):
    _, sd, sha1, _ = indexed
    sym = symbols(sd, sha1)
    types = defs_of(sym, "web/src/types.ts")
    assert types[("Invoice", "interface")]["range"] == [1, 4]
    assert ("ApiResponse", "interface") in types
    assert "Invoice" not in ref_names(sym, "web/src/types.ts")

    api = sym["files"]["web/src/api.ts"]
    assert defs_of(sym, "web/src/api.ts")[("fetchInvoice", "function")]["range"] == [3, 6]
    assert api["imports"] == [{"module": "./types", "line": 1, "resolved": "web/src/types.ts"}]
    assert {"ApiResponse", "Invoice", "fetch"} <= ref_names(sym, "web/src/api.ts")

    index = sym["files"]["web/src/index.ts"]
    assert index["imports"] == [{"module": "./api", "line": 1, "resolved": "web/src/api.ts"}]
    ref = next(r for r in index["refs"] if r["name"] == "fetchInvoice")
    assert (ref["line"], ref["col"]) == (3, 0)


def test_go(indexed):
    _, sd, sha1, _ = indexed
    sym = symbols(sd, sha1)
    queue = defs_of(sym, "worker/queue.go")
    assert queue[("Queue", "struct")]["range"] == [3, 5]
    assert queue[("Push", "method")]["parent"] == "Queue"
    assert queue[("Pop", "method")]["parent"] == "Queue"
    assert "parent" not in queue[("NewQueue", "function")]
    assert "Queue" not in {r["name"] for r in sym["files"]["worker/queue.go"]["refs"] if r["line"] == 3}

    main = sym["files"]["worker/main.go"]
    assert {"NewQueue", "Push", "Pop", "Println"} <= ref_names(sym, "worker/main.go")
    assert main["imports"] == [{"module": "fmt", "line": 3, "resolved": None}]


def test_sql_tables(indexed):
    _, sd, sha1, _ = indexed
    sym = symbols(sd, sha1)
    schema = defs_of(sym, "db/schema.sql")
    assert schema[("users", "table")]["range"] == [1, 4]
    assert schema[("invoices", "table")]["range"] == [6, 10]
    assert sym["files"]["db/schema.sql"]["imports"] == []


def test_indexed_flags(indexed):
    _, sd, sha1, _ = indexed
    files = tree(sd, sha1)
    sym = symbols(sd, sha1)
    assert files["README.md"]["indexed"] is False
    assert "README.md" not in sym["files"]
    assert files[".gitignore"]["indexed"] is False  # language null
    for path in ("app/main.py", "web/src/api.ts", "worker/queue.go", "db/schema.sql"):
        assert files[path]["indexed"] is True
        assert path in sym["files"]
    assert set(sym["files"]) == {p for p, f in files.items() if f["indexed"]}


def test_reindex_is_idempotent(indexed):
    kb, sd, sha1, _ = indexed
    snap = sd / "snapshots" / sha1
    before = ((snap / "symbols.json").read_bytes(), (snap / "tree.json").read_bytes())
    _run("index", str(kb), "demo", "--sha", sha1)
    after = ((snap / "symbols.json").read_bytes(), (snap / "tree.json").read_bytes())
    assert before == after


def test_unparseable_file_does_not_abort(indexed, monkeypatch, capsys):
    from readcode import indexer

    kb, sd, sha1, _ = indexed
    real = indexer.extract

    def flaky(source, language, path, paths):
        if path == "app/models.py":
            raise RuntimeError("boom")
        return real(source, language, path, paths)

    monkeypatch.setattr(indexer, "extract", flaky)
    result = indexer.index_snapshot(kb, "demo", sha1)
    assert result["failed"] == 1
    err = capsys.readouterr().err
    assert "app/models.py (RuntimeError)" in err and err.count("\n") == 1
    assert tree(sd, sha1)["app/models.py"]["indexed"] is False
    assert "app/models.py" not in symbols(sd, sha1)["files"]
    assert "app/main.py" in symbols(sd, sha1)["files"]
    monkeypatch.undo()
    assert indexer.index_snapshot(kb, "demo", sha1)["failed"] == 0  # restore for other tests
    assert tree(sd, sha1)["app/models.py"]["indexed"] is True


def test_index_missing_snapshot_errors(indexed):
    kb, _, _, _ = indexed
    r = runner.invoke(app, ["index", str(kb), "demo", "--sha", "0" * 40])
    assert r.exit_code == 1
    assert "error" in r.output


def test_extract_edge_cases():
    from readcode.indexer import extract

    src = "X = 1\nclass C:\n    def m(self):\n        def inner():\n            pass\n".encode()
    defs = {d["name"]: d for d in extract(src, "python", "p.py", frozenset())["defs"]}
    assert defs["X"]["kind"] == "constant"
    assert defs["m"]["kind"] == "method" and defs["m"]["parent"] == "C"
    assert defs["inner"]["kind"] == "function" and "parent" not in defs["inner"]

    ref = extract("ñ = f(1)\n".encode(), "python", "p.py", frozenset())["refs"][0]
    assert (ref["name"], ref["line"], ref["col"]) == ("f", 1, 4)  # columns in characters


def test_cli_summary_counts_failures(indexed, monkeypatch):
    from readcode import indexer

    kb, sd, sha1, _ = indexed
    real = indexer.extract

    def flaky(source, language, path, paths):
        if path in ("app/models.py", "app/main.py"):
            raise ValueError("boom")
        return real(source, language, path, paths)

    monkeypatch.setattr(indexer, "extract", flaky)
    r = runner.invoke(app, ["index", str(kb), "demo", "--sha", sha1])
    assert r.exit_code == 0, r.output
    assert "(2 con errores)" in r.output
    assert "aviso: no se pudo indexar app/main.py (ValueError)" in r.output
    monkeypatch.undo()
    _run("index", str(kb), "demo", "--sha", sha1)


def test_index_upgrades_unexplained_partial_to_indexed(indexed):
    kb, sd, sha1, _ = indexed
    statuses = {s["sha"]: s["status"] for s in kbio.read_json(sd / "study.json")["snapshots"]}
    assert statuses[sha1] == "indexed"  # snapshot left it "partial", nothing explained yet


def test_index_keeps_partial_when_explanations_exist(tmp_path, fixture_repo):
    repo, sha1, _ = fixture_repo
    kb = tmp_path / "kb"
    _run("init", str(kb), "demo", "--repo", str(repo))
    _run("snapshot", str(kb), "demo", "--sha", sha1)
    sd = kb / "demo"
    kbio.atomic_write_text(sd / "snapshots" / sha1 / "explain" / "app" / "main.py.json", "{}")
    _run("index", str(kb), "demo", "--sha", sha1)
    assert kbio.read_json(sd / "study.json")["snapshots"][0]["status"] == "partial"
    _run("mark", str(kb), "demo", "--sha", sha1, "--status", "explained")
    _run("index", str(kb), "demo", "--sha", sha1)
    assert kbio.read_json(sd / "study.json")["snapshots"][0]["status"] == "explained"
