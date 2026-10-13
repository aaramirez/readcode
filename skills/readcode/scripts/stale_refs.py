"""Find reused study docs that may have gone stale after an update (shaA -> shaB).

Usage: python stale_refs.py <kb-dir> <study> <shaA> <shaB>

Needs <study>/diffs/<A>..<B>/changes.json (run `readcode diff` first) and the
tree/symbols of both snapshots. A definition "changed" when its file was added
or deleted, or when it exists on only one side or its lines differ (modified or
renamed files). Prints JSON with:

  changedSymbols  {path: [names]} definitions that changed
  explain         unchanged files of B whose explanation exists and whose code
                  references a changed name (symbols.json refs, names the file
                  does not define itself) or whose Markdown has a [[ref]] to a
                  changed file or to an unpathed changed symbol
  dirs, tours, overview   reused docs whose markers point at changed files;
                  tours also list steps whose path changed (1-based)

Stdlib only; never writes anything.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REF_RE = re.compile(r"\[\[ref:([^\]\n]*)\]\]")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _resolve(study_data: dict, prefix: str) -> str:
    shas = [s["sha"] for s in study_data.get("snapshots", [])]
    matches = [s for s in shas if s == prefix] or [s for s in shas if prefix and s.startswith(prefix)]
    if len(matches) != 1:
        raise SystemExit(f"error: {prefix!r} is not a unique studied snapshot")
    return matches[0]


def _lines(study: Path, blob: str | None) -> list[str]:
    if not blob:
        return []
    path = study / "blobs" / blob[:2] / f"{blob}.txt"
    text = path.read_bytes().decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _def_texts(defs: list[dict], lines: list[str]) -> dict[tuple, str]:
    out = {}
    for d in defs:
        s, e = d["range"]
        out[(d.get("parent"), d["name"])] = "\n".join(lines[s - 1:e])
    return out


def _marker_targets(text: str) -> list[tuple[str, str | None]]:
    """(path, symbol) of each [[ref:...]] marker; path "" when unpathed."""
    out = []
    for body in _REF_RE.findall(text):
        target = body.split("|", 1)[0]
        if "#" in target:
            path, sym = target.split("#", 1)
            out.append((path, sym.rsplit(".", 1)[-1]))
        else:
            out.append((target.split(":L", 1)[0], None))
    return out


def _stale_markers(text: str, changed: dict[str, list[str]], gone: set[str],
                   changed_paths: set[str], unpathed: set[str]) -> list[str]:
    """Markers that may now point at the wrong thing.

    Line markers into any changed file (lines shift), symbol markers to a changed
    definition or into a deleted/renamed-away file, and unpathed #symbol markers
    whose name is in ``unpathed``.
    """
    hits = []
    for path, sym in _marker_targets(text):
        if path == "":
            if sym and sym in unpathed:
                hits.append(f"#{sym}")
        elif sym is None and path in changed_paths:
            hits.append(path)
        elif sym is not None and (path in gone or sym in changed.get(path, [])):
            hits.append(f"{path}#{sym}")
    return sorted(set(hits))


def stale_refs(kb: Path, study_name: str, sha_a: str, sha_b: str) -> dict:
    study = Path(kb) / study_name
    study_data = _load(study / "study.json")
    if not study_data:
        raise SystemExit(f"error: {study / 'study.json'} not found")
    sha_a, sha_b = _resolve(study_data, sha_a), _resolve(study_data, sha_b)
    changes = _load(study / "diffs" / f"{sha_a}..{sha_b}" / "changes.json")
    if not changes:
        raise SystemExit("error: changes.json missing; run `readcode diff` first")
    snap_a, snap_b = study / "snapshots" / sha_a, study / "snapshots" / sha_b
    sym_a = _load(snap_a / "symbols.json").get("files", {})
    sym_b = _load(snap_b / "symbols.json").get("files", {})

    changed: dict[str, list[str]] = {}
    changed_paths: set[str] = set()
    gone: set[str] = set()
    for f in changes["files"]:
        new_path, old_path = f["path"], f.get("oldPath", f["path"])
        changed_paths.update({new_path, old_path})
        if f["status"] == "deleted":
            gone.add(new_path)
        elif f["status"] == "renamed":
            gone.add(old_path)
        old_defs = sym_a.get(old_path, {}).get("defs", []) if f["status"] != "added" else []
        new_defs = sym_b.get(new_path, {}).get("defs", []) if f["status"] != "deleted" else []
        old_t = _def_texts(old_defs, _lines(study, f.get("fromBlob")))
        new_t = _def_texts(new_defs, _lines(study, f.get("toBlob")))
        names = {key[1] for key in old_t.keys() | new_t.keys() if old_t.get(key) != new_t.get(key)}
        if names:
            changed[new_path] = sorted(names)
    changed_names = {n for names in changed.values() for n in names}

    tree_b = _load(snap_b / "tree.json").get("files", [])
    explain = []
    for info in tree_b:
        path = info["path"]
        doc_path = snap_b / "explain" / f"{path}.json"
        if path in changed_paths or not doc_path.is_file():
            continue
        own = {d["name"] for d in sym_b.get(path, {}).get("defs", [])}
        code = sorted({r["name"] for r in sym_b.get(path, {}).get("refs", [])
                       if r["name"] in changed_names and r["name"] not in own})
        markers = _stale_markers(doc_path.read_text(encoding="utf-8"), changed, gone, changed_paths,
                                 changed_names)
        if code or markers:
            explain.append({"path": path, "symbols": code, "markers": markers})

    dirs = []
    for doc_path in sorted((snap_b / "dirs").rglob("*.json")) if (snap_b / "dirs").is_dir() else []:
        markers = _stale_markers(doc_path.read_text(encoding="utf-8"), changed, gone,
                                 changed_paths, set())
        if markers:
            rel = doc_path.relative_to(snap_b / "dirs").as_posix()[: -len(".json")]
            dirs.append({"path": "" if rel == "_root" else rel, "markers": markers})

    tours = []
    for doc_path in sorted((snap_b / "tours").glob("*.json")) if (snap_b / "tours").is_dir() else []:
        doc = _load(doc_path)
        steps = [i for i, s in enumerate(doc.get("steps", []), 1) if s.get("path") in changed_paths]
        markers = _stale_markers(doc_path.read_text(encoding="utf-8"), changed, gone,
                                 changed_paths, set())
        if steps or markers:
            tours.append({"id": doc_path.stem, "steps": steps, "markers": markers})

    overview = snap_b / "overview.md"
    overview_markers = []
    if overview.is_file():
        overview_markers = _stale_markers(overview.read_text(encoding="utf-8"), changed, gone,
                                          changed_paths, set())
    return {"from": sha_a, "to": sha_b, "changedSymbols": changed, "explain": explain,
            "dirs": dirs, "tours": tours, "overview": overview_markers}


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(stale_refs(Path(argv[0]), argv[1], argv[2], argv[3]), indent=2,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
