"""Filesystem helpers for a readcode knowledge base (atomic writes, JSON, paths, hashing)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (temp file in same dir, fsync, os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path | str, text: str) -> None:
    """Atomically write ``text`` as UTF-8 (no newline translation)."""
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path | str, data: object) -> None:
    """Atomically write JSON: UTF-8, indent 2, ensure_ascii False, trailing newline."""
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path | str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def study_dir(kb: Path | str, study: str) -> Path:
    return Path(kb) / study


def blob_path(study_directory: Path | str, blob_hash: str) -> Path:
    """``<study>/blobs/<first2>/<hash>.txt``."""
    return Path(study_directory) / "blobs" / blob_hash[:2] / f"{blob_hash}.txt"


def snapshot_dir(study_directory: Path | str, sha: str) -> Path:
    """``<study>/snapshots/<sha>``."""
    return Path(study_directory) / "snapshots" / sha


def explain_path(snapshot_directory: Path | str, file_path: str) -> Path:
    """``<snapshot>/explain/<path>.json`` (e.g. ``explain/app/main.py.json``)."""
    return Path(snapshot_directory) / "explain" / f"{file_path}.json"


def dir_summary_path(snapshot_directory: Path | str, dir_path: str) -> Path:
    """``<snapshot>/dirs/<path>.json``; the repo root ("") is ``dirs/_root.json``."""
    name = dir_path if dir_path else "_root"
    return Path(snapshot_directory) / "dirs" / f"{name}.json"


def resolve_sha(study_data: dict, prefix: str) -> str:
    """Resolve a full sha or unique prefix against study.json snapshots; ValueError if not studied."""
    shas = [s["sha"] for s in study_data.get("snapshots", [])]
    if prefix in shas:
        return prefix
    matches = [s for s in shas if prefix and s.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"Snapshot {prefix!r} is not part of the study; run `readcode snapshot` first")
    raise ValueError(f"Ambiguous sha prefix {prefix!r}: {', '.join(matches)}")
