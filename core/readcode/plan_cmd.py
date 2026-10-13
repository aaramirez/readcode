"""``readcode plan``: resumable work queue for the LLM skill (reuse, pending files/dirs, batches)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path, PurePosixPath

from readcode import kbio


class PlanError(RuntimeError):
    pass


def _date(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["date"].replace("Z", "+00:00"))


def _has_explain(sdir: Path, sha: str) -> bool:
    d = kbio.snapshot_dir(sdir, sha) / "explain"
    return d.is_dir() and any(d.rglob("*.json"))


def _safe_entries(sdir: Path, snapshots: list) -> list[dict]:
    """study.json snapshot entries whose sha is a safe snapshot dir; the rest are skipped with a warning."""
    out = []
    for s in snapshots:
        try:
            if not isinstance(s, dict) or not isinstance(s.get("date"), str):
                print(f"aviso: se omite una entrada de study.json sin fecha: {s!r}", file=sys.stderr)
                continue
            kbio.safe_snapshot_dir(sdir, s.get("sha"))
        except kbio.UnsafeSnapshotError as exc:
            print(f"aviso: se omite un snapshot de study.json: {exc}", file=sys.stderr)
            continue
        out.append(s)
    return out


def reuse_source(sdir: Path, study_data: dict, sha: str) -> str | None:
    """Snapshot ``plan`` inherits from (reported as ``reusedFrom``).

    Most recent earlier snapshot with explain/ files; otherwise any other (newest first).
    """
    snaps = sorted(_safe_entries(sdir, study_data["snapshots"]), key=_date)
    this = next((s for s in snaps if s["sha"] == sha), None)
    others = [s for s in snaps if s["sha"] != sha]
    if this is not None:
        earlier = [s for s in others if _date(s) < _date(this)]
        later = [s for s in others if _date(s) >= _date(this)]
        ordered = list(reversed(earlier)) + list(reversed(later))
    else:
        ordered = list(reversed(others))
    for s in ordered:
        if _has_explain(sdir, s["sha"]):
            return s["sha"]
    return None


def _explain_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return kbio.read_json(path).get("blobHash")
    except (ValueError, AttributeError):
        return None


def _parents(path: str) -> list[str]:
    """All ancestor directories of a file path, nearest first, ending with "" (root)."""
    out, cur = [], PurePosixPath(path).parent
    while str(cur) != ".":
        out.append(str(cur))
        cur = cur.parent
    out.append("")
    return out


def _abandoned(snap: Path) -> tuple[set[str], set[str]]:
    """(files, dirs) given up by the generator: issues.json entries with source "generator"
    whose file is ``explain/<path>.json`` or ``dirs/<path>.json`` (root: ``dir-root.json``, or the
    v1 ``dirs/_root.json`` when the tree has no directory named ``_root``)."""
    path = snap / "issues.json"
    if not path.is_file():
        return set(), set()
    try:
        issues = kbio.read_json(path).get("issues", [])
    except (ValueError, AttributeError):
        return set(), set()
    files, dirs = set(), set()
    legacy_root = not kbio.has_root_named_dir(snap)
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict) or issue.get("source") != "generator":
            continue
        f = issue.get("file")
        if not isinstance(f, str) or not f.endswith(".json"):
            continue
        if f.startswith("explain/"):
            files.add(f[len("explain/"):-len(".json")])
        elif f == kbio.ROOT_DIR_DOC:
            dirs.add("")
        elif f.startswith("dirs/"):
            d = f[len("dirs/"):-len(".json")]
            dirs.add("" if d == "_root" and legacy_root else d)
    return files, dirs


def _subtrees(files: list[dict]) -> dict[str, dict[str, str]]:
    """Directory -> {path: blob} of every file below it (the root is "")."""
    out: dict[str, dict[str, str]] = {}
    for f in files:
        for d in _parents(f["path"]):
            out.setdefault(d, {})[f["path"]] = f["blob"]
    return out


def _batches(pending: list[dict], limit: int) -> list[dict]:
    """Greedy packing over files ordered by parent dir, so directories stay together."""
    ordered = sorted(pending, key=lambda f: (str(PurePosixPath(f["path"]).parent), f["path"]))
    batches: list[list[dict]] = []
    cur: list[dict] = []
    total = 0
    for f in ordered:
        if cur and total + f["lines"] > limit:
            batches.append(cur)
            cur, total = [], 0
        cur.append({"path": f["path"], "lines": f["lines"], "language": f["language"]})
        total += f["lines"]
    if cur:
        batches.append(cur)
    return [{"id": f"batch-{i:03d}", "files": files} for i, files in enumerate(batches, 1)]


def plan_snapshot(kb: Path | str, study: str, sha: str, batch_lines: int = 1500) -> dict:
    sdir = kbio.study_dir(kb, study)
    study_json = sdir / "study.json"
    if not study_json.is_file():
        raise PlanError(f"{study_json} not found; run `readcode init` first")
    study_data = kbio.read_json(study_json)
    try:
        sha = kbio.resolve_sha(study_data, sha, sdir)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc
    snap = kbio.snapshot_dir(sdir, sha)
    tree_path = snap / "tree.json"
    if not tree_path.is_file():
        raise PlanError(f"{tree_path} not found; run `readcode snapshot` first")
    tree = kbio.read_json(tree_path)

    explainable = [f for f in tree["files"] if not (f["language"] is None and f["bytes"] == 0)]

    other = reuse_source(sdir, study_data, sha)
    given_up, given_up_dirs = _abandoned(snap)
    reused = 0
    pending: list[dict] = []
    abandoned: list[str] = []
    for f in explainable:
        mine = kbio.explain_path(snap, f["path"])
        if other is not None and not mine.is_file():
            theirs = kbio.explain_path(kbio.snapshot_dir(sdir, other), f["path"])
            if _explain_hash(theirs) == f["blob"]:
                kbio.atomic_write_bytes(mine, theirs.read_bytes())
                reused += 1
        if _explain_hash(mine) != f["blob"]:
            if f["path"] in given_up:
                abandoned.append(f["path"])
            else:
                pending.append(f)

    all_dirs = {d for f in tree["files"] for d in _parents(f["path"])} | {""}
    dirty = {d for f in pending for d in _parents(f["path"])}
    reused_dirs = 0
    if other is not None:
        other_dir = kbio.snapshot_dir(sdir, other)
        other_tree = other_dir / "tree.json"
        old_files = kbio.read_json(other_tree)["files"] if other_tree.is_file() else []
        # A summary is inherited only when its whole subtree (paths and blobs) is identical;
        # the overview only when the whole tree is.
        old_sub, new_sub = _subtrees(old_files), _subtrees(tree["files"])
        same_tree = old_sub.get("", {}) == new_sub.get("", {})
        for d in all_dirs:
            if d in dirty or old_sub.get(d) != new_sub.get(d):
                continue
            theirs = kbio.find_dir_summary(other_dir, d)  # a v1 root is inherited under its new name
            if kbio.find_dir_summary(snap, d) is None and theirs is not None:
                kbio.atomic_write_bytes(kbio.dir_summary_path(snap, d), theirs.read_bytes())
                reused_dirs += 1
        # Copied only into a snapshot that never had the directory: once it exists (even
        # emptied by the user) deleted tours/diagrams are not resurrected on later runs.
        for sub in ("tours", "diagrams"):
            src = other_dir / sub
            if src.is_dir() and not (snap / sub).exists():
                for f in src.rglob("*"):
                    dest = snap / sub / f.relative_to(src)
                    if f.is_file() and not dest.exists():
                        kbio.atomic_write_bytes(dest, f.read_bytes())
        if same_tree and not pending and not (snap / "overview.md").is_file():
            ov = other_dir / "overview.md"
            if ov.is_file():
                kbio.atomic_write_bytes(snap / "overview.md", ov.read_bytes())

    unsummarized = [d for d in all_dirs if d in dirty or kbio.find_dir_summary(snap, d) is None]
    pending_dirs = [d for d in unsummarized if d not in given_up_dirs]
    pending_dirs.sort(key=lambda d: (-(len(d.split("/")) if d else 0), d))
    abandoned_dirs = sorted(d for d in unsummarized if d in given_up_dirs)

    tours = snap / "tours"
    tours_pending = not (tours.is_dir() and any(tours.iterdir()))
    overview_pending = not (snap / "overview.md").is_file() or bool(pending)

    result = {
        "sha": sha,
        "reusedFrom": other,
        "reused": reused,
        "reusedDirs": reused_dirs,
        "batches": _batches(pending, batch_lines),
        "dirs": pending_dirs,
        "overview": overview_pending,
        "tours": tours_pending,
        "abandoned": sorted(abandoned),
        "abandonedDirs": abandoned_dirs,
        "done": not (pending or pending_dirs or overview_pending or tours_pending),
    }
    kbio.atomic_write_json(snap / "plan.json", result)
    return result


def summarize(plan: dict) -> str:
    nfiles = sum(len(b["files"]) for b in plan["batches"])
    return (
        f"Plan {plan['sha']}: {plan['reused']} explicaciones y {plan['reusedDirs']} directorios reutilizados, "
        f"{nfiles} archivos pendientes en {len(plan['batches'])} lotes, "
        f"{len(plan['dirs'])} directorios pendientes, "
        f"{len(plan['abandoned'])} archivos y {len(plan['abandonedDirs'])} directorios abandonados, "
        f"overview={'pendiente' if plan['overview'] else 'ok'}, "
        f"tours={'pendientes' if plan['tours'] else 'ok'}, "
        f"{'completo' if plan['done'] else 'incompleto'}"
    )
