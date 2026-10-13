"""``readcode plan``: resumable work queue for the LLM skill (reuse, pending files/dirs, batches)."""

from __future__ import annotations

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


def _reuse_source(sdir: Path, study_data: dict, sha: str) -> str | None:
    """Most recent earlier snapshot with explain/ files; otherwise any other (newest first)."""
    snaps = sorted(study_data["snapshots"], key=_date)
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
        sha = kbio.resolve_sha(study_data, sha)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc
    snap = kbio.snapshot_dir(sdir, sha)
    tree_path = snap / "tree.json"
    if not tree_path.is_file():
        raise PlanError(f"{tree_path} not found; run `readcode snapshot` first")
    tree = kbio.read_json(tree_path)

    explainable = [f for f in tree["files"] if not (f["language"] is None and f["bytes"] == 0)]

    other = _reuse_source(sdir, study_data, sha)
    reused = 0
    pending: list[dict] = []
    for f in explainable:
        mine = kbio.explain_path(snap, f["path"])
        if other is not None and not mine.is_file():
            theirs = kbio.explain_path(kbio.snapshot_dir(sdir, other), f["path"])
            if _explain_hash(theirs) == f["blob"]:
                kbio.atomic_write_bytes(mine, theirs.read_bytes())
                reused += 1
        if _explain_hash(mine) != f["blob"]:
            pending.append(f)

    all_dirs = {d for f in tree["files"] for d in _parents(f["path"])} | {""}
    dirty = {d for f in pending for d in _parents(f["path"])}
    reused_dirs = 0
    changed_set = False
    if other is not None:
        other_dir = kbio.snapshot_dir(sdir, other)
        other_tree = other_dir / "tree.json"
        old_paths = [f["path"] for f in kbio.read_json(other_tree)["files"]] if other_tree.is_file() else []
        new_paths = [f["path"] for f in tree["files"]]
        changed_set = set(old_paths) != set(new_paths)
        old_sets: dict[str, set[str]] = {}
        new_sets: dict[str, set[str]] = {}
        for paths, sets in ((old_paths, old_sets), (new_paths, new_sets)):
            for path in paths:
                for d in _parents(path):
                    sets.setdefault(d, set()).add(path)
        for d in all_dirs:
            if d in dirty or old_sets.get(d) != new_sets.get(d):
                continue
            mine, theirs = kbio.dir_summary_path(snap, d), kbio.dir_summary_path(other_dir, d)
            if not mine.is_file() and theirs.is_file():
                kbio.atomic_write_bytes(mine, theirs.read_bytes())
                reused_dirs += 1
        for sub in ("tours", "diagrams"):
            src = other_dir / sub
            if src.is_dir():
                for f in src.rglob("*"):
                    dest = snap / sub / f.relative_to(src)
                    if f.is_file() and not dest.exists():
                        kbio.atomic_write_bytes(dest, f.read_bytes())
        if not pending and not changed_set and not (snap / "overview.md").is_file():
            ov = other_dir / "overview.md"
            if ov.is_file():
                kbio.atomic_write_bytes(snap / "overview.md", ov.read_bytes())

    pending_dirs = [d for d in all_dirs if d in dirty or not kbio.dir_summary_path(snap, d).is_file()]
    pending_dirs.sort(key=lambda d: (-(len(d.split("/")) if d else 0), d))

    tours = snap / "tours"
    tours_pending = not (tours.is_dir() and any(tours.iterdir()))
    overview_pending = not (snap / "overview.md").is_file() or bool(pending)

    result = {
        "sha": sha,
        "reused": reused,
        "reusedDirs": reused_dirs,
        "batches": _batches(pending, batch_lines),
        "dirs": pending_dirs,
        "overview": overview_pending,
        "tours": tours_pending,
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
        f"overview={'pendiente' if plan['overview'] else 'ok'}, "
        f"tours={'pendientes' if plan['tours'] else 'ok'}, "
        f"{'completo' if plan['done'] else 'incompleto'}"
    )
