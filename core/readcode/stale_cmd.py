"""``readcode stale``: reused docs that may have gone stale after an update (shaA -> shaB).

Needs ``diffs/<A>..<B>/changes.json`` (``readcode diff``). A definition "changed" when its file
was added or deleted, or when it exists on only one side or its lines differ (modified or
renamed files). Reported docs of snapshot B:

- ``explain``: unchanged files with an explanation whose code references a changed name
  (symbols.json refs, excluding names the file defines itself) or whose Markdown has a marker
  that may now point at the wrong thing;
- ``dirs``, ``tours`` (plus steps on changed files, 1-based) and ``overview``: markers only.

A marker may be stale when it is a line marker into a changed file, a symbol marker to a changed
definition or into a deleted / renamed-away file, or an unpathed ``#symbol`` with a changed name.
"""

from __future__ import annotations

from pathlib import Path

from readcode import kbio, refs
from readcode.schemas import validate


class StaleError(RuntimeError):
    pass


def _read(path: Path) -> dict:
    try:
        data = kbio.read_json(path) if path.is_file() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _lines(sdir: Path, blob: str | None) -> list[str]:
    if not blob:
        return []
    path = kbio.blob_path(sdir, blob)
    try:
        return kbio.blob_lines(path.read_bytes())
    except OSError as exc:
        raise StaleError(f"blob {blob} unreadable ({path}): {exc.strerror or exc}; "
                         "re-run `readcode snapshot` for both commits") from exc


def _def_texts(defs: list[dict], lines: list[str]) -> dict[tuple, str]:
    return {(d.get("parent"), d["name"]): "\n".join(lines[d["range"][0] - 1:d["range"][1]])
            for d in defs}


class _Changes:
    def __init__(self, changed: dict[str, list[str]], paths: set[str], gone: set[str]):
        self.changed, self.paths, self.gone = changed, paths, gone
        self.names = {n for names in changed.values() for n in names}

    def markers(self, texts: list[str]) -> list[str]:
        hits = set()
        for text in texts:
            for m in refs.parse_markers(text.replace("\r\n", "\n").replace("\r", "\n")):
                if m.kind == "lines" and m.path in self.paths:
                    hits.add(m.path)
                elif m.kind == "symbol":
                    name = (m.symbol or "").rpartition(".")[2]
                    if m.path is None:
                        if name in self.names:
                            hits.add(f"#{m.symbol}")
                    elif m.path in self.gone or name in self.changed.get(m.path, []):
                        hits.add(f"{m.path}#{m.symbol}")
        return sorted(hits)


def stale_docs(kb: Path | str, study: str, sha_a: str, sha_b: str) -> dict:
    sdir = kbio.study_dir(kb, study)
    if not (sdir / "study.json").is_file():
        raise StaleError(f"{sdir / 'study.json'} not found; run `readcode init` first")
    study_data = kbio.read_json(sdir / "study.json")
    try:
        sha_a, sha_b = kbio.resolve_sha(study_data, sha_a), kbio.resolve_sha(study_data, sha_b)
    except ValueError as exc:
        raise StaleError(str(exc)) from exc
    changes_path = sdir / "diffs" / f"{sha_a}..{sha_b}" / "changes.json"
    if not changes_path.is_file():
        raise StaleError(f"changes.json for {sha_a}..{sha_b} missing; run `readcode diff` first")
    try:
        changes = kbio.read_json(changes_path)
    except (OSError, ValueError) as exc:
        raise StaleError(f"{changes_path} is not valid JSON ({exc}); "
                         "regenerate it with `readcode diff`") from exc
    errors = validate("changes", changes)
    if errors:
        raise StaleError(f"{changes_path} is malformed ({errors[0]}); "
                         "regenerate it with `readcode diff`")
    snap_a, snap_b = kbio.snapshot_dir(sdir, sha_a), kbio.snapshot_dir(sdir, sha_b)
    sym_a = _read(snap_a / "symbols.json").get("files", {})
    sym_b = _read(snap_b / "symbols.json").get("files", {})

    changed: dict[str, list[str]] = {}
    paths: set[str] = set()
    gone: set[str] = set()
    for f in changes["files"]:
        new_path, old_path = f["path"], f.get("oldPath", f["path"])
        paths.update({new_path, old_path})
        if f["status"] == "deleted":
            gone.add(new_path)
        elif f["status"] == "renamed":
            gone.add(old_path)
        old_defs = sym_a.get(old_path, {}).get("defs", []) if f["status"] != "added" else []
        new_defs = sym_b.get(new_path, {}).get("defs", []) if f["status"] != "deleted" else []
        old_t = _def_texts(old_defs, _lines(sdir, f.get("fromBlob")))
        new_t = _def_texts(new_defs, _lines(sdir, f.get("toBlob")))
        names = {k[1] for k in old_t.keys() | new_t.keys() if old_t.get(k) != new_t.get(k)}
        if names:
            changed[new_path] = sorted(names)
    ch = _Changes(changed, paths, gone)

    explain = []
    for info in _read(snap_b / "tree.json").get("files", []):
        path = info["path"]
        doc = _read(kbio.explain_path(snap_b, path))
        if path in paths or not doc:
            continue
        own = {d["name"] for d in sym_b.get(path, {}).get("defs", [])}
        code = sorted({r["name"] for r in sym_b.get(path, {}).get("refs", [])
                       if r["name"] in ch.names and r["name"] not in own})
        markers = ch.markers([doc.get("summary", "")] + [b.get("body", "") for b in doc.get("blocks", [])])
        if code or markers:
            explain.append({"path": path, "symbols": code, "markers": markers})

    dirs = []
    dirs_root = snap_b / "dirs"
    docs: list[tuple[str, Path]] = []
    for doc_path in sorted(dirs_root.rglob("*.json")) if dirs_root.is_dir() else []:
        rel = doc_path.relative_to(dirs_root).as_posix()[: -len(".json")]
        if rel == "_root" and kbio.legacy_root_path(snap_b) is not None:
            continue  # the v1 root summary: read below, unless dir-root.json replaces it
        docs.append((rel, doc_path))
    root_doc = kbio.find_dir_summary(snap_b, "")
    if root_doc is not None:
        docs.insert(0, ("", root_doc))
    for rel, doc_path in docs:
        markers = ch.markers([_read(doc_path).get("summary", "")])
        if markers:
            dirs.append({"path": rel, "markers": markers})

    tours = []
    tours_root = snap_b / "tours"
    for doc_path in sorted(tours_root.glob("*.json")) if tours_root.is_dir() else []:
        doc = _read(doc_path)
        st = doc.get("steps", [])
        steps = [i for i, s in enumerate(st, 1) if s.get("path") in paths]
        markers = ch.markers([doc.get("description", "")] + [s.get("body", "") for s in st])
        if steps or markers:
            tours.append({"id": doc_path.stem, "steps": steps, "markers": markers})

    overview = snap_b / "overview.md"
    ov = ch.markers([overview.read_text(encoding="utf-8")]) if overview.is_file() else []
    return {"from": sha_a, "to": sha_b, "changedSymbols": changed, "explain": explain,
            "dirs": dirs, "tours": tours, "overview": ov}


def format_stale(r: dict) -> str:
    out = [f"Stale {r['from'][:7]}..{r['to'][:7]}"]
    for path, names in r["changedSymbols"].items():
        out.append(f"  cambiado {path}: {', '.join(names)}")
    for e in r["explain"]:
        out.append(f"  explain {e['path']}: símbolos [{', '.join(e['symbols'])}] "
                   f"marcadores [{', '.join(e['markers'])}]")
    for d in r["dirs"]:
        out.append(f"  dir {d['path'] or '(raíz)'}: marcadores [{', '.join(d['markers'])}]")
    for t in r["tours"]:
        out.append(f"  tour {t['id']}: pasos {t['steps']} marcadores [{', '.join(t['markers'])}]")
    if r["overview"]:
        out.append(f"  overview: marcadores [{', '.join(r['overview'])}]")
    if len(out) == 1:
        out.append("  nada que refrescar")
    return "\n".join(out)
