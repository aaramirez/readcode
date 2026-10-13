"""Print the context a subagent needs to explain some files of a readcode snapshot.

Usage: python file_context.py <snapshot-dir> <path> [<path> ...]

For each repo path prints (JSON): language, lines, the blob file holding the exact
snapshot content (read it instead of the working copy), definitions, imports,
files that import it, files that reference its definitions, graph neighbours
(when graph/graph.json exists) and whether an explanation already exists.

Stdlib only; never writes anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

USED_BY_LIMIT = 15
NEIGHBOUR_LIMIT = 20


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _graph_neighbours(graph: dict, path: str) -> list[str]:
    nodes = {n.get("id"): n for n in graph.get("nodes", [])}
    out: list[str] = []
    for link in graph.get("links", []):
        a, b = nodes.get(link.get("source")), nodes.get(link.get("target"))
        if not a or not b:
            continue
        for mine, other, arrow in ((a, b, "->"), (b, a, "<-")):
            if mine.get("source_file") == path and other.get("source_file") not in (None, path):
                item = (f"{mine.get('label')} {arrow} {link.get('relation', 'rel')} "
                        f"{other.get('source_file')}#{other.get('label')}")
                if item not in out:
                    out.append(item)
    return out[:NEIGHBOUR_LIMIT]


def file_context(snap: Path, paths: list[str]) -> list[dict]:
    study = snap.resolve().parent.parent
    tree = {f["path"]: f for f in _load(snap / "tree.json").get("files", [])}
    files = _load(snap / "symbols.json").get("files", {})
    graph = _load(snap / "graph" / "graph.json")
    result = []
    for path in paths:
        info = tree.get(path)
        if info is None:
            result.append({"path": path, "error": "not in tree.json"})
            continue
        syms = files.get(path, {"defs": [], "refs": [], "imports": []})
        names = {d["name"] for d in syms["defs"]}
        imported_by = sorted(p for p, s in files.items() if p != path
                             and any(i.get("resolved") == path for i in s.get("imports", [])))
        hits: dict[str, set[str]] = {}
        for p, s in files.items():
            if p == path:
                continue
            for r in s.get("refs", []):
                if r["name"] in names:
                    hits.setdefault(p, set()).add(r["name"])
        used_by = sorted(hits.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:USED_BY_LIMIT]
        explain = snap / "explain" / f"{path}.json"
        current = _load(explain).get("blobHash") == info["blob"] if explain.is_file() else False
        result.append({
            "path": path,
            "language": info["language"],
            "lines": info["lines"],
            "blobFile": str(study / "blobs" / info["blob"][:2] / f"{info['blob']}.txt"),
            "blobHash": info["blob"],
            "indexed": info["indexed"],
            "defs": [f"{d['name']} ({d['kind']}{', in ' + d['parent'] if d.get('parent') else ''}) "
                     f"L{d['range'][0]}-{d['range'][1]}" for d in syms["defs"]],
            "imports": [f"{i['module']} -> {i.get('resolved')}" for i in syms["imports"]],
            "importedBy": imported_by,
            "usedBy": {p: sorted(n) for p, n in used_by},
            "graphNeighbours": _graph_neighbours(graph, path) if graph else [],
            "explanation": ("current" if current else "stale") if explain.is_file() else "missing",
        })
    return result


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    snap = Path(argv[0])
    if not (snap / "tree.json").is_file():
        print(f"error: {snap / 'tree.json'} not found", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(file_context(snap, argv[1:]), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
