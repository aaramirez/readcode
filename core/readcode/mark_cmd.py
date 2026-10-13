"""``readcode mark``: the only study.json fields the skill sets (snapshot status, archify tool)."""

from __future__ import annotations

from pathlib import Path

from readcode import kbio
from readcode.schemas import validate

STATUSES = ("indexed", "explained", "partial")


class MarkError(RuntimeError):
    pass


def mark_study(kb: Path | str, study: str, sha: str | None = None, status: str | None = None,
               archify: bool | None = None) -> dict:
    """Set a snapshot's ``status`` and/or ``tools.archify``; returns the new study.json."""
    if (status is None) != (sha is None):
        raise MarkError("--status and --sha go together")
    if status is None and archify is None:
        raise MarkError("nothing to mark: pass --status (with --sha) and/or --archify")
    if status is not None and status not in STATUSES:
        raise MarkError(f"--status must be one of {', '.join(STATUSES)}")
    path = kbio.study_dir(kb, study) / "study.json"
    if not path.is_file():
        raise MarkError(f"{path} not found; run `readcode init` first")
    data = kbio.read_json(path)
    if status is not None:
        try:
            full = kbio.resolve_sha(data, sha)
        except ValueError as exc:
            raise MarkError(str(exc)) from exc
        next(s for s in data["snapshots"] if s["sha"] == full)["status"] = status
    if archify is not None:
        data.setdefault("tools", {"graphify": False, "archify": False})["archify"] = archify
    errors = validate("study", data)
    if errors:
        raise MarkError("Invalid study: " + "; ".join(errors))
    kbio.atomic_write_json(path, data)
    return data
