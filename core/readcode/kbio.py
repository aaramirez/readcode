"""Filesystem helpers for a readcode knowledge base (atomic writes, JSON, paths, hashing)."""

from __future__ import annotations

import hashlib
import json
import os
import re
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


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class UnsafeSnapshotError(ValueError):
    """A snapshot sha that is not 40-hex or whose directory resolves outside ``<study>/snapshots``."""


def safe_snapshot_dir(study_directory: Path | str, sha: str) -> Path:
    """``<study>/snapshots/<sha>`` for a 40-hex sha whose resolved path (symlinks and junctions
    followed) stays directly under ``<study>/snapshots``; otherwise UnsafeSnapshotError."""
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        raise UnsafeSnapshotError(f"sha de snapshot no válido: {sha!r} (se esperan 40 caracteres hexadecimales)")
    snap = snapshot_dir(study_directory, sha)
    root = (Path(study_directory) / "snapshots").resolve()
    if root.parent != Path(study_directory).resolve() or snap.resolve().parent != root:
        raise UnsafeSnapshotError(f"el snapshot {sha} resuelve fuera de {Path(study_directory) / 'snapshots'}")
    return snap


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


def resolve_sha(study_data: dict, prefix: str, sdir: Path | str | None = None) -> str:
    """Resolve a full sha or unique prefix against study.json snapshots; ValueError if not studied.

    Entries that are not 40-hex are ignored. With ``sdir`` the result must also pass
    ``safe_snapshot_dir`` (UnsafeSnapshotError, a ValueError, otherwise)."""
    shas = [s["sha"] for s in study_data.get("snapshots", [])
            if isinstance(s, dict) and isinstance(s.get("sha"), str) and SHA_RE.match(s["sha"])]
    if prefix in shas:
        found = prefix
    else:
        matches = [s for s in shas if prefix and s.startswith(prefix)]
        if not matches:
            raise ValueError(f"el snapshot {prefix!r} no es parte del estudio; ejecuta `readcode snapshot` primero")
        if len(matches) > 1:
            raise ValueError(f"prefijo de sha ambiguo {prefix!r}: {', '.join(matches)}")
        found = matches[0]
    if sdir is not None:
        safe_snapshot_dir(sdir, found)
    return found
