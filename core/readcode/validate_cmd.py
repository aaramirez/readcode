"""`readcode validate`: the gate every generated study file passes through.

Checks schemas, explain/tour ranges and markers, and writes ``links.json``
(for every snapshot and every diff validated) plus the snapshot ``issues.json`` and
``search.json`` (every block of every schema-valid explanation, for the viewer's Ctrl+K).

Problem ``file`` values are paths relative to the study directory
(``snapshots/<sha>/explain/app/x.py.json``). In ``issues.json`` the same
problems are stored with ``file`` relative to the snapshot directory, i.e. the
same key the doc has in ``links.json``. Problems of study.json and of diffs are
only reported on output (issues.json is per snapshot).

The root directory summary is ``dir-root.json``. A v1 kb has it at ``dirs/_root.json``; that is
read as the root (key ``dirs/_root.json``) only when tree.json has no directory named ``_root``
and ``dir-root.json`` is absent, and ``readcode migrate`` renames it. It is reported with the
warning code ``legacy-root`` (problems whose ``code`` is in ``WARNING_CODES`` do not fail the run).

Doc keys in ``links.json`` are the doc's path relative to the snapshot (or diff) directory,
except tour steps: a tour's description is ``tours/<id>.json`` and step ``n`` (1-based) is
``tours/<id>.json#<n>``, because each step resolves markers relative to its own file.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from readcode import kbio, refs, schemas
from readcode.schemas import validate as schema_validate

_DIFF_DIR_RE = re.compile(r"^([0-9a-f]{40})\.\.([0-9a-f]{40})$")
_DIAGRAM_NAME_RE = refs._ARCHIFY_RE  # same rule as [[archify:name]]
_EMPTY_TREE: dict = {"files": []}
_EMPTY_SYMBOLS: dict = {"files": {}}


WARNING_CODES = frozenset({"legacy-root"})


class ValidateError(RuntimeError):
    """The study or the requested snapshot cannot be validated at all."""


class _Collector:
    def __init__(self) -> None:
        self.problems: list[dict] = []

    def add(self, file: str, problem: str, hint: str, code: str | None = None) -> None:
        self.problems.append({"file": file, "problem": problem, "hint": hint,
                              **({"code": code} if code else {})})


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _load(path: Path, kind: str, rel: str, out: _Collector) -> dict | None:
    """Read JSON and validate against ``kind``; None (and a problem) if unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        out.add(rel, f"unreadable JSON: {exc}", "write valid UTF-8 JSON")
        return None
    errors = schema_validate(kind, data)
    for err in errors:
        out.add(rel, f"schema {kind}: {err}", f"fix the field to match {schemas.SCHEMAS_DIR / f'{kind}.schema.json'}")
    return None if errors else data


def _range_problem(rng: list[int], lines: int | None) -> str | None:
    start, end = rng
    if start > end:
        return f"range {start}-{end} has start > end"
    if lines is not None and end > lines:
        return f"range {start}-{end} is outside the file ({lines} lines)"
    return None


class _Resolver:
    """Resolves markdown markers for one doc set; collects link entries and problems."""

    def __init__(self, tree: dict, symbols: dict, diagrams: set[str],
                 fallback: tuple[dict, dict] | None = None) -> None:
        self.tree, self.symbols, self.diagrams = tree, symbols, diagrams
        self.fallback = fallback
        self.docs: dict[str, list[dict]] = {}

    def doc(self, key: str) -> None:
        self.docs.setdefault(key, [])

    def markdown(self, key: str, rel: str, text: str, current_path: str | None,
                 where: str, out: _Collector) -> None:
        entries = self.docs.setdefault(key, [])
        for marker in refs.parse_markers(_lf(text)):
            res = refs.resolve(marker, current_path, self.tree, self.symbols, self.diagrams)
            from_a = False
            if res.status == "broken" and self.fallback and marker.kind in ("symbol", "lines"):
                alt = refs.resolve(marker, current_path, *self.fallback, self.diagrams)
                if alt.status != "broken":
                    res, from_a = alt, True
            entry = res.to_link_entry()
            if from_a:
                entry["snapshot"] = "A"  # only resolves in snapshot A; B-resolved refs omit it
            # The viewer looks markers up by raw text within a doc key: one raw, one meaning.
            if any(e["raw"] == entry["raw"] and e != entry for e in entries):
                out.add(rel, f"marker {res.raw} in {where} resolves differently elsewhere in "
                             f"the same doc ({key})",
                        "report this as a readcode bug (each doc key needs one resolution per marker)")
            entries.append(entry)
            self._report(res, rel, where, out)

    @staticmethod
    def _report(res: refs.Resolution, rel: str, where: str, out: _Collector) -> None:
        if res.kind == "invalid":
            out.add(rel, f"invalid marker {res.raw} in {where}",
                    "use [[ref:path#symbol]], [[ref:path:L10-31]] or [[archify:name]]")
        elif res.status == "broken" and res.kind == "archify":
            out.add(rel, f"broken reference {res.raw} in {where}",
                    f"create {res.target} or remove the marker")
        elif res.status == "broken":
            out.add(rel, f"broken reference {res.raw} in {where}",
                    "check the path, symbol name and line range against tree.json/symbols.json")
        elif res.status == "exact" and (
                res.target is None or (res.kind in ("symbol", "lines") and res.range is None)):
            out.add(rel, f"internal: exact resolution of {res.raw} lacks target/range",
                    "report this as a readcode bug")

    def links(self, sha: str, diagrams: list[dict] | None = None) -> dict:
        links: dict = {"schemaVersion": 1, "sha": sha, "docs": self.docs}
        if diagrams is not None:
            links["diagrams"] = diagrams
        return links


def _diagram_list(snap: Path, sp: str = "", out: _Collector | None = None) -> list[dict]:
    """Explicit diagrams/ listing: archify (.html) and mermaid (.mmd), sorted by name.

    Names that break the diagram-name rule are skipped (and reported when ``out`` is given).
    """
    base = snap / "diagrams"
    if not base.is_dir():
        return []
    found = []
    for pattern, kind in (("*.html", "archify"), ("*.mmd", "mermaid")):
        for p in base.glob(pattern):
            if not p.is_file():
                continue
            if not _DIAGRAM_NAME_RE.match(p.stem):
                if out is not None:
                    out.add(f"{sp}/diagrams/{p.name}" if sp else f"diagrams/{p.name}",
                            f"diagram name {p.stem!r} is not valid and was skipped",
                            "rename it using only [A-Za-z0-9._-] and no '..'")
                continue
            found.append({"name": p.stem, "kind": kind})
    return sorted(found, key=lambda d: (d["name"], d["kind"]))


def _rel_json_files(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*.json") if p.is_file())


def _write_links(path: Path, links: dict, rel: str, out: _Collector) -> None:
    for err in schema_validate("links", links):
        out.add(rel, f"internal: generated links.json invalid: {err}", "report this as a readcode bug")
    kbio.atomic_write_json(path, links)


# --------------------------------------------------------------- snapshot


def _check_explain(snap: Path, sp: str, rel_path: str, files: dict, res: _Resolver,
                   search: list[dict], out: _Collector) -> None:
    key = f"explain/{rel_path}"
    rel = f"{sp}/{key}"
    res.doc(key)
    doc = _load(snap / key, "explain", rel, out)
    if doc is None:
        return
    location = rel_path[: -len(".json")]
    if doc["path"] != location:
        out.add(rel, f"path {doc['path']!r} does not match its location ({location!r})",
                f"set \"path\": \"{location}\" or move the file")
    search.extend({"path": location, "blockId": b["id"], "title": b["title"],
                   "range": b["range"]} for b in doc["blocks"])
    info = files.get(location)
    lines = None
    if info is None:
        out.add(rel, f"explained file {location!r} is not in tree.json",
                "delete this explanation or check the path")
    else:
        lines = info["lines"]
        if doc["blobHash"] != info["blob"]:
            out.add(rel, "stale explanation: blobHash differs from the tree blob",
                    "re-explain the file (its content changed)")
    seen: set[str] = set()
    prev: tuple[str, list[int]] | None = None
    for block in doc["blocks"]:
        bid, rng = block["id"], block["range"]
        if bid in seen:
            out.add(rel, f"duplicate block id {bid}", "give each block a unique id (b1, b2, ...)")
        seen.add(bid)
        bad = _range_problem(rng, lines)
        if bad:
            out.add(rel, f"block {bid}: {bad}", "fix the block range to lie within the file")
            continue
        if prev is not None:
            pid, prng = prev
            if rng[0] < prng[0]:
                out.add(rel, f"block {bid} starts before block {pid}: blocks not sorted by start",
                        "order blocks by start line")
            elif rng[0] <= prng[1]:
                out.add(rel, f"block {bid} ({rng[0]}-{rng[1]}) overlaps block {pid} "
                             f"({prng[0]}-{prng[1]})", "make block ranges disjoint")
        prev = (bid, rng)
    res.markdown(key, rel, doc["summary"], location, "summary", out)
    for block in doc["blocks"]:
        res.markdown(key, rel, block["body"], location, f"block {block['id']}", out)


def _check_dir(snap: Path, sp: str, key: str, location: str, res: _Resolver, out: _Collector) -> None:
    """One directory summary: ``key`` is its doc key (path relative to the snapshot)."""
    rel = f"{sp}/{key}"
    res.doc(key)
    doc = _load(snap / key, "dir", rel, out)
    if doc is None:
        return
    if doc["path"] != location:
        out.add(rel, f"path {doc['path']!r} does not match its location ({location!r})",
                f"set \"path\": \"{location}\""
                + (f" (root directory = \"\", stored as {kbio.ROOT_DIR_DOC})" if not location else ""))
    res.markdown(key, rel, doc["summary"], location, "summary", out)


def _check_tour(snap: Path, sp: str, rel_path: str, files: dict, res: _Resolver,
                out: _Collector) -> None:
    key = f"tours/{rel_path}"
    rel = f"{sp}/{key}"
    res.doc(key)
    doc = _load(snap / key, "tour", rel, out)
    if doc is None:
        return
    tour_id = rel_path[: -len(".json")]
    if doc["id"] != tour_id:
        out.add(rel, f"tour id {doc['id']!r} does not match the file name",
                f"set \"id\": \"{tour_id}\"")
    res.markdown(key, rel, doc["description"], None, "description", out)
    # Each step resolves relative to its own file, so it gets its own doc key.
    for i, step in enumerate(doc["steps"], 1):
        info = files.get(step["path"])
        if info is None:
            out.add(rel, f"tour step {i}: file {step['path']!r} is not in tree.json",
                    "use a path listed in tree.json")
        else:
            bad = _range_problem(step["range"], info["lines"])
            if bad:
                out.add(rel, f"tour step {i}: {bad}", "fix the step range")
        res.markdown(f"{key}#{i}", rel, step["body"], step["path"], f"step {i}", out)


def _validate_snapshot(sdir: Path, sha: str, out: _Collector, derived_only: bool = False) -> None:
    snap = kbio.snapshot_dir(sdir, sha)
    sp = f"snapshots/{sha}"
    if not snap.is_dir():
        out.add(sp, "snapshot directory missing", "run `readcode snapshot` for this sha")
        return
    start = len(out.problems)
    tree = _EMPTY_TREE
    if (snap / "tree.json").is_file():
        tree = _load(snap / "tree.json", "tree", f"{sp}/tree.json", out) or _EMPTY_TREE
    else:
        out.add(f"{sp}/tree.json", "tree.json missing", "run `readcode snapshot` for this sha")
    symbols = _EMPTY_SYMBOLS
    if (snap / "symbols.json").is_file():
        symbols = _load(snap / "symbols.json", "symbols", f"{sp}/symbols.json", out) or _EMPTY_SYMBOLS
    files = {f["path"]: f for f in tree["files"]}
    diagrams = {p.name for p in (snap / "diagrams").glob("*.html")} if (snap / "diagrams").is_dir() else set()
    res = _Resolver(tree, symbols, diagrams)
    search: list[dict] = []

    for rel_path in _rel_json_files(snap / "explain"):
        _check_explain(snap, sp, rel_path, files, res, search, out)
    legacy_root = kbio.legacy_root_path(snap)  # None when dirs/_root.json is a real directory's
    if (snap / kbio.ROOT_DIR_DOC).is_file():
        _check_dir(snap, sp, kbio.ROOT_DIR_DOC, "", res, out)
    for rel_path in _rel_json_files(snap / "dirs"):
        location = rel_path[: -len(".json")]
        key = f"dirs/{rel_path}"
        if location == "_root" and legacy_root is not None:
            out.add(f"{sp}/{key}", "legacy root summary: v1 stored the root at dirs/_root.json",
                    f"run `readcode migrate` to move it to {kbio.ROOT_DIR_DOC}", code="legacy-root")
            if (snap / kbio.ROOT_DIR_DOC).is_file():
                continue  # dir-root.json wins
            location = ""
        _check_dir(snap, sp, key, location, res, out)
    for rel_path in _rel_json_files(snap / "tours"):
        _check_tour(snap, sp, rel_path, files, res, out)
    overview = snap / "overview.md"
    if overview.is_file():
        try:
            text = overview.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            out.add(f"{sp}/overview.md", f"unreadable: {exc}", "write overview.md as UTF-8")
            text = ""
        res.markdown("overview.md", f"{sp}/overview.md", text, None, "overview", out)

    _write_links(snap / "links.json", res.links(sha, _diagram_list(snap, sp, out)), f"{sp}/links.json", out)
    for err in schema_validate("search", search):
        out.add(f"{sp}/search.json", f"internal: generated search.json invalid: {err}",
                "report this as a readcode bug")
    kbio.atomic_write_json(snap / "search.json", search)
    if not derived_only:  # derived-only leaves issues.json (generator and validate entries) untouched
        _write_issues(snap, sp, out.problems[start:], out)


def _write_issues(snap: Path, sp: str, problems: list[dict], out: _Collector) -> None:
    path = snap / "issues.json"
    kept: list[dict] = []
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if not schema_validate("issues", old):
                kept = [i for i in old["issues"] if i.get("source") != "validate"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    prefix = f"{sp}/"
    new = [{"file": p["file"][len(prefix):] if p["file"].startswith(prefix) else p["file"],
            "problem": p["problem"], "hint": p["hint"], "source": "validate",
            **({"code": p["code"]} if "code" in p else {})} for p in problems]
    kbio.atomic_write_json(path, {"schemaVersion": 1, "issues": kept + new})


# ------------------------------------------------------------------ diffs


def _snapshot_index(sdir: Path, sha: str) -> tuple[dict, dict]:
    """tree/symbols of a snapshot for marker resolution (empty when absent/invalid)."""
    out = []
    snap = _safe_snapshot_dir(sdir, sha)
    if snap is None:
        return _EMPTY_TREE, _EMPTY_SYMBOLS
    for name, kind, empty in (("tree.json", "tree", _EMPTY_TREE),
                              ("symbols.json", "symbols", _EMPTY_SYMBOLS)):
        try:
            data = json.loads((snap / name).read_text(encoding="utf-8"))
            out.append(empty if schema_validate(kind, data) else data)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            out.append(empty)
    return out[0], out[1]


def _validate_diff(sdir: Path, name: str, out: _Collector) -> None:
    ddir = sdir / "diffs" / name
    dp = f"diffs/{name}"
    m = _DIFF_DIR_RE.match(name)
    if not m:
        out.add(dp, "diff directory name is not <shaA>..<shaB> (40-hex shas)",
                "regenerate it with `readcode diff`")
        return
    sha_a, sha_b = m.groups()
    if not _is_safe_diff_dir(sdir, name):
        out.add(dp, "diff directory resolves outside <study>/diffs; skipped",
                "replace the link with a real directory or regenerate it with `readcode diff`")
        return
    unsafe = [s for s in (sha_a, sha_b) if _safe_snapshot_dir(sdir, s) is None]
    if unsafe:
        out.add(dp, f"snapshot {unsafe[0]} is not a safe snapshot directory (resolves outside "
                    "<study>/snapshots); its files are not read", "replace the link with a real snapshot")
    changes = None
    if (ddir / "changes.json").is_file():
        changes = _load(ddir / "changes.json", "changes", f"{dp}/changes.json", out)
        if changes and (changes["from"], changes["to"]) != (sha_a, sha_b):
            out.add(f"{dp}/changes.json", "from/to do not match the directory name",
                    "regenerate it with `readcode diff`")
    else:
        out.add(f"{dp}/changes.json", "changes.json missing", "run `readcode diff` first")
    by_path = {f["path"]: f for f in changes["files"]} if changes else {}

    tree_b, symbols_b = _snapshot_index(sdir, sha_b)
    res = _Resolver(tree_b, symbols_b, set(), fallback=_snapshot_index(sdir, sha_a))
    snap_b = _safe_snapshot_dir(sdir, sha_b)
    if snap_b is not None and (snap_b / "diagrams").is_dir():
        res.diagrams = {p.name for p in (snap_b / "diagrams").glob("*.html")}

    if (ddir / "explain.md").is_file():
        try:
            text = (ddir / "explain.md").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            out.add(f"{dp}/explain.md", f"unreadable: {exc}", "write explain.md as UTF-8")
            text = ""
        res.markdown("explain.md", f"{dp}/explain.md", text, None, "explain.md", out)
    for rel_path in _rel_json_files(ddir / "explain"):
        key = f"explain/{rel_path}"
        rel = f"{dp}/{key}"
        res.doc(key)
        doc = _load(ddir / key, "diff-explain", rel, out)
        if doc is None:
            continue
        location = rel_path[: -len(".json")]
        if doc["path"] != location:
            out.add(rel, f"path {doc['path']!r} does not match its location ({location!r})",
                    f"set \"path\": \"{location}\" or move the file")
        change = by_path.get(location)
        if changes is not None and change is None:
            out.add(rel, f"file {location!r} is not in changes.json", "explain only changed files")
        res.markdown(key, rel, doc["summary"], location, "summary", out)
        for hunk in doc["hunks"]:
            if change is not None and hunk["index"] >= len(change["hunks"]):
                out.add(rel, f"hunk index {hunk['index']} does not exist "
                             f"({len(change['hunks'])} hunks in changes.json)",
                        "use 0-based indexes into the file's hunks")
            res.markdown(key, rel, hunk["body"], location, f"hunk {hunk['index']}", out)
    _write_links(ddir / "links.json", res.links(sha_b), f"{dp}/links.json", out)


# ------------------------------------------------------------------- main


def validate_study(kb: Path | str, study: str, sha: str | None = None,
                   derived_only: bool = False) -> list[dict]:
    """Validate a study (one snapshot with ``sha``, else all snapshots and diffs).

    ``derived_only`` rewrites only links.json and search.json (byte-identical to a full run) and
    leaves issues.json alone, so generator issues survive; the problems returned are informational.

    Returns problems ``[{file, problem, hint}]``; writes links.json / issues.json.
    Raises ValidateError when study.json is missing or ``sha`` is not studied.
    """
    sdir = kbio.study_dir(kb, study)
    if not (sdir / "study.json").is_file():
        raise ValidateError(f"{sdir / 'study.json'} not found; run `readcode init` first")
    out = _Collector()
    study_data = _load(sdir / "study.json", "study", "study.json", out)
    if study_data is None:
        try:
            study_data = json.loads((sdir / "study.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            study_data = {}
        if not isinstance(study_data, dict):
            study_data = {}
    shas = []
    for s in study_data.get("snapshots", []) if isinstance(study_data.get("snapshots"), list) else []:
        if not (isinstance(s, dict) and isinstance(s.get("sha"), str)):
            continue
        if _safe_snapshot_dir(sdir, s["sha"]) is None:
            out.add("study.json", f"snapshot sha {s['sha']!r} is not a safe 40-hex sha; skipped",
                    "use the full lowercase 40-hex commit sha")
            continue
        shas.append(s["sha"])
    if sha is not None:
        try:
            shas = [kbio.resolve_sha({"snapshots": [{"sha": s} for s in shas]}, sha, sdir)]
        except ValueError as exc:
            raise ValidateError(str(exc)) from exc
    for s in shas:
        _validate_snapshot(sdir, s, out, derived_only)
    diffs = sdir / "diffs"
    if diffs.is_dir():
        for d in sorted(p.name for p in diffs.iterdir() if p.is_dir()):
            if sha is None or d.endswith(f"..{shas[0]}"):
                _validate_diff(sdir, d, out)
    return out.problems


def is_warning(problem: dict) -> bool:
    return problem.get("code") in WARNING_CODES


def format_problems(problems: list[dict]) -> str:
    if not problems:
        return "OK: sin problemas"
    return "\n".join(f"{'aviso: ' if is_warning(p) else ''}{p['file']}: {p['problem']} ({p['hint']})"
                     for p in problems)


# ---------------------------------------------------------------- refresh

_DERIVED_NAMES = frozenset({"links.json", "search.json", "issues.json"})


def _safe_snapshot_dir(sdir: Path, sha: str) -> Path | None:
    """``<study>/snapshots/<sha>`` only for a 40-hex sha that stays under ``<study>/snapshots``."""
    try:
        return kbio.safe_snapshot_dir(sdir, sha)
    except kbio.UnsafeSnapshotError:
        return None


def _is_safe_diff_dir(sdir: Path, name: str) -> bool:
    """``<study>/diffs/<name>`` stays directly under ``<study>/diffs`` (no link escapes)."""
    root = (sdir / "diffs").resolve()
    return root.parent == sdir.resolve() and (sdir / "diffs" / name).resolve().parent == root


def _study_shas(sdir: Path) -> list[str]:
    data = json.loads((sdir / "study.json").read_text(encoding="utf-8"))
    snaps = data.get("snapshots", []) if isinstance(data, dict) else []
    if not isinstance(snaps, list):
        return []
    return [s["sha"] for s in snaps
            if isinstance(s, dict) and isinstance(s.get("sha"), str)
            and _safe_snapshot_dir(sdir, s["sha"]) is not None]


def is_stale(sdir: Path) -> bool:
    """True when a derived links.json is missing or older than a source file of the study."""
    dirs = [d for d in (kbio.snapshot_dir(sdir, s) for s in _study_shas(sdir)) if d.is_dir()]
    diffs = sdir / "diffs"
    if diffs.is_dir():
        dirs += [d for d in sorted(diffs.iterdir()) if d.is_dir() and _DIFF_DIR_RE.match(d.name)
                 and _is_safe_diff_dir(sdir, d.name)]
    if not dirs:
        return False
    links = [d / "links.json" for d in dirs]
    if not all(p.is_file() for p in links):
        return True
    oldest = min(p.stat().st_mtime for p in links)
    return any(p.stat().st_mtime > oldest
               for d in dirs for p in d.rglob("*")
               if p.is_file() and not (p.parent == d and p.name in _DERIVED_NAMES))


def refresh_stale(kb: Path | str, echo=None) -> list[str]:
    """Regenerate derived files of every stale study in ``kb``; return their names.

    A study that fails is skipped with one warning (``echo``, default stderr); the rest go on.
    """
    if echo is None:
        def echo(msg: str) -> None:
            print(msg, file=sys.stderr)
    kb = Path(kb)
    done: list[str] = []
    for sdir in sorted(p for p in kb.iterdir() if (p / "study.json").is_file()):
        try:
            if is_stale(sdir):
                validate_study(kb, sdir.name, derived_only=True)
                done.append(sdir.name)
        except Exception as exc:  # one broken study must not stop the others
            echo(f"aviso: no se pudieron regenerar los derivados de {sdir.name} ({exc}); se omite")
    return done
