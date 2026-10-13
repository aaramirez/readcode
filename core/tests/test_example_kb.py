"""The committed example study (examples/kb/fixture) must stay valid and complete."""
import json
import re
import shutil
from pathlib import Path, PurePosixPath

import pytest

from readcode.validate_cmd import validate_study

EXAMPLE_KB = Path(__file__).resolve().parents[2] / "examples" / "kb"
STUDY = EXAMPLE_KB / "fixture"


@pytest.fixture(scope="module")
def kb_copy(tmp_path_factory):
    # validate rewrites links.json/issues.json: work on a copy so the test never touches git files
    dest = tmp_path_factory.mktemp("kb") / "kb"
    shutil.copytree(EXAMPLE_KB, dest)
    return dest


def _study():
    return json.loads((STUDY / "study.json").read_text(encoding="utf-8"))


def test_example_validates_without_problems(kb_copy):
    assert validate_study(kb_copy, "fixture") == []


def test_every_snapshot_is_fully_explained():
    study = _study()
    assert len(study["snapshots"]) == 2
    for snap in study["snapshots"]:
        assert snap["status"] == "explained"
        sdir = STUDY / "snapshots" / snap["sha"]
        tree = json.loads((sdir / "tree.json").read_text(encoding="utf-8"))
        dirs = {""}
        for f in tree["files"]:
            assert (sdir / "explain" / f"{f['path']}.json").is_file(), f["path"]
            parent = PurePosixPath(f["path"]).parent
            while str(parent) != ".":
                dirs.add(str(parent))
                parent = parent.parent
        for d in dirs:
            assert (sdir / "dirs" / f"{d or '_root'}.json").is_file(), d
        assert (sdir / "overview.md").is_file()
        assert len(list((sdir / "tours").glob("*.json"))) >= 2
        assert (sdir / "diagrams" / "arquitectura.html").is_file()


def test_diff_is_explained():
    study = _study()
    a, b = (s["sha"] for s in study["snapshots"])
    ddir = STUDY / "diffs" / f"{a}..{b}"
    changes = json.loads((ddir / "changes.json").read_text(encoding="utf-8"))
    assert (ddir / "explain.md").is_file()
    for f in changes["files"]:
        doc = json.loads((ddir / "explain" / f"{f['path']}.json").read_text(encoding="utf-8"))
        assert sorted(h["index"] for h in doc["hunks"]) == list(range(len(f["hunks"])))


_LEAK_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]\w"  # Windows drive paths (C:\x, C:/x), not "http://"
    r"|[\\/]Users[\\/]|/home/|AppData"
    r"|Alexander[ _]Ramirez",  # the author's user name
    re.IGNORECASE,
)


def _strings(node):
    """All strings (keys and values) of a JSON document, unescaped."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_example_has_no_machine_paths():
    assert "localPath" not in _study()["repo"]
    for p in EXAMPLE_KB.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".mmd", ".html"}:
            text = p.read_text(encoding="utf-8")
            if p.suffix == ".json":  # scan decoded strings: JSON escapes like "\n" are not paths
                text = "\n".join(_strings(json.loads(text)))
            m = _LEAK_RE.search(text)
            assert m is None, f"{p}: {m.group(0) if m else ''}"
