"""``readcode context``: what a skill subagent needs to explain some files of a snapshot."""

from __future__ import annotations

from pathlib import Path

from readcode import kbio

USED_BY_LIMIT = 15
NEIGHBOUR_LIMIT = 20


class ContextError(RuntimeError):
    pass


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


def _read(path: Path) -> dict:
    try:
        data = kbio.read_json(path) if path.is_file() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def file_context(kb: Path | str, study: str, sha: str, paths: list[str]) -> list[dict]:
    """Per path: blob file, defs, imports, importers, users, graph neighbours, explanation state."""
    sdir = kbio.study_dir(kb, study)
    if not (sdir / "study.json").is_file():
        raise ContextError(f"{sdir / 'study.json'} not found; run `readcode init` first")
    try:
        sha = kbio.resolve_sha(kbio.read_json(sdir / "study.json"), sha)
    except ValueError as exc:
        raise ContextError(str(exc)) from exc
    snap = kbio.snapshot_dir(sdir, sha)
    if not (snap / "tree.json").is_file():
        raise ContextError(f"{snap / 'tree.json'} not found; run `readcode snapshot` first")
    tree = {f["path"]: f for f in _read(snap / "tree.json").get("files", [])}
    files = _read(snap / "symbols.json").get("files", {})
    graph = _read(snap / "graph" / "graph.json")
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
        explain = kbio.explain_path(snap, path)
        state = "missing"
        if explain.is_file():
            state = "current" if _read(explain).get("blobHash") == info["blob"] else "stale"
        result.append({
            "path": path,
            "language": info["language"],
            "lines": info["lines"],
            "blobFile": str(kbio.blob_path(sdir.resolve(), info["blob"])),
            "blobHash": info["blob"],
            "indexed": info["indexed"],
            "defs": [f"{d['name']} ({d['kind']}{', in ' + d['parent'] if d.get('parent') else ''}) "
                     f"L{d['range'][0]}-{d['range'][1]}" for d in syms["defs"]],
            "imports": [f"{i['module']} -> {i.get('resolved')}" for i in syms["imports"]],
            "importedBy": imported_by,
            "usedBy": {p: sorted(n) for p, n in used_by},
            "graphNeighbours": _graph_neighbours(graph, path) if graph else [],
            "explanation": state,
        })
    return result


def format_context(items: list[dict]) -> str:
    out = []
    for c in items:
        if "error" in c:
            out.append(f"{c['path']}: {c['error']}")
            continue
        out.append(f"{c['path']} ({c['language']}, {c['lines']} líneas, explicación: {c['explanation']})")
        out.append(f"  blob: {c['blobFile']}")
        out.append(f"  blobHash: {c['blobHash']}")
        for key in ("defs", "imports", "importedBy", "graphNeighbours"):
            if c[key]:
                out.append(f"  {key}: " + "; ".join(c[key]))
        if c["usedBy"]:
            out.append("  usedBy: " + "; ".join(f"{p} ({', '.join(n)})" for p, n in c["usedBy"].items()))
    return "\n".join(out)
