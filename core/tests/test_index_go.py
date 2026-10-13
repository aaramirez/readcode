import subprocess

from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.indexer import extract, _parse_go_module
from readcode.schemas import validate

runner = CliRunner()

FILES = {
    "go.mod": "module github.com/x/y\n\ngo 1.22\n",
    "main.go": 'package main\n\nimport (\n\t"fmt"\n\t"github.com/x/y/internal/app"\n\t"github.com/x/y/nogo"\n'
               '\t"github.com/x/y"\n\t"github.com/other/z/internal/app"\n)\n\nfunc main() { fmt.Println(app.X) }\n',
    "internal/app/app.go": 'package app\n\nimport "errors"\n\nvar ErrX = errors.New("x")\n\n'
                           'var (\n\tA, B = 1, 2\n\tC int\n)\n\nconst (\n\tOne = iota\n\tTwo\n)\n\n'
                           'func F() {\n\tvar local = 1\n\tconst k = 2\n\t_ = local\n}\n',
    "nogo/readme.md": "# x\n",
    "sub/go.mod": "module example.com/sub\n",
    "sub/main.go": 'package main\n\nimport (\n\t"example.com/sub/pkg"\n\t"github.com/x/y/internal/app"\n)\n',
    "sub/pkg/p.go": "package pkg\n",
}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _index(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    kb = tmp_path / "kb"
    for args in (("init", str(kb), "demo", "--repo", str(repo)),
                 ("snapshot", str(kb), "demo", "--sha", sha),
                 ("index", str(kb), "demo", "--sha", sha)):
        r = runner.invoke(app, list(args))
        assert r.exit_code == 0, r.output
    sym = kbio.read_json(kb / "demo" / "snapshots" / sha / "symbols.json")
    assert validate("symbols", sym) == []
    return sym, r


def test_go_import_resolved_dir_and_nested_module(tmp_path):
    sym, _ = _index(tmp_path, FILES)
    imports = {i["module"]: i for i in sym["files"]["main.go"]["imports"]}
    assert imports["github.com/x/y/internal/app"] == {
        "module": "github.com/x/y/internal/app", "line": 5, "resolved": None,
        "resolvedDir": "internal/app"}
    for unresolved in ("fmt", "github.com/x/y/nogo", "github.com/x/y", "github.com/other/z/internal/app"):
        assert "resolvedDir" not in imports[unresolved] and imports[unresolved]["resolved"] is None
    # nested module resolves against its own go.mod, not the root one
    sub = {i["module"]: i for i in sym["files"]["sub/main.go"]["imports"]}
    assert sub["example.com/sub/pkg"]["resolvedDir"] == "sub/pkg"
    assert "resolvedDir" not in sub["github.com/x/y/internal/app"]


def test_go_package_vars_and_consts(tmp_path):
    sym, _ = _index(tmp_path, FILES)
    defs = {(d["name"], d["kind"]): d["range"] for d in sym["files"]["internal/app/app.go"]["defs"]}
    assert defs[("ErrX", "variable")] == [5, 5]
    assert defs[("A", "variable")] == [8, 8] and defs[("B", "variable")] == [8, 8]
    assert defs[("C", "variable")] == [9, 9]
    assert defs[("One", "constant")] == [13, 13] and defs[("Two", "constant")] == [14, 14]
    assert ("F", "function") in defs
    assert not {"local", "k"} & {n for n, _ in defs}


def test_go_mod_without_module_warns_once(tmp_path):
    files = dict(FILES, **{"go.mod": "go 1.22\n"})
    sym, r = _index(tmp_path, files)
    assert all("resolvedDir" not in i for i in sym["files"]["main.go"]["imports"])
    assert r.output.count("línea `module` de go.mod") == 1


def test_parse_go_module():
    assert _parse_go_module("// c\nmodule github.com/a/b // x\n") == "github.com/a/b"
    assert _parse_go_module('module "a.b/c"\n') == "a.b/c"
    assert _parse_go_module("go 1.22\n") is None


def test_extract_without_go_modules_leaves_unresolved():
    out = extract(b'package a\nimport "x/y"\n', "go", "a.go", frozenset({"a.go"}))
    assert out["imports"] == [{"module": "x/y", "line": 2, "resolved": None}]
