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


def blob_lines(data: bytes) -> list[str]:
    r"""Lines of a blob as readcode numbers them (tree.json ``lines``, ranges, hunks).

    UTF-8 with errors="replace", split ONLY on "\n" (a trailing "\r" per line is dropped, so
    CRLF counts as one break; \f, \x85, U+2028 or a lone \r do not break lines). A final
    newline does not start an extra line; empty data has no lines.
    """
    lines = data.decode("utf-8", errors="replace").split("\n")
    if lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


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


ROOT_DIR_DOC = "dir-root.json"
LEGACY_ROOT_DIR_DOC = "dirs/_root.json"


def dir_summary_path(snapshot_directory: Path | str, dir_path: str) -> Path:
    """``<snapshot>/dirs/<path>.json``; the repo root ("") is ``<snapshot>/dir-root.json``,
    outside ``dirs/`` so it cannot collide with a repo directory (e.g. one named ``_root``)."""
    if not dir_path:
        return Path(snapshot_directory) / ROOT_DIR_DOC
    return Path(snapshot_directory) / "dirs" / f"{dir_path}.json"


def has_root_named_dir(snapshot_directory: Path | str) -> bool:
    """True when the snapshot's tree.json has a directory named ``_root`` (any path under ``_root/``)."""
    try:
        files = read_json(Path(snapshot_directory) / "tree.json").get("files", [])
    except (OSError, ValueError, AttributeError):
        return False
    return any(isinstance(f, dict) and str(f.get("path", "")).startswith("_root/") for f in files)


def legacy_root_path(snapshot_directory: Path | str) -> Path | None:
    """The v1 root summary ``dirs/_root.json``, when it is to be read as the root summary:
    the file exists and the tree has no directory named ``_root`` (then it is that directory's)."""
    path = Path(snapshot_directory) / LEGACY_ROOT_DIR_DOC
    if path.is_file() and not has_root_named_dir(snapshot_directory):
        return path
    return None


def find_dir_summary(snapshot_directory: Path | str, dir_path: str) -> Path | None:
    """Existing summary file of a directory; for the root, ``dir-root.json`` wins over a legacy
    ``dirs/_root.json``. None when there is none."""
    path = dir_summary_path(snapshot_directory, dir_path)
    if path.is_file():
        return path
    return legacy_root_path(snapshot_directory) if not dir_path else None


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
