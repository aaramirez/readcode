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
