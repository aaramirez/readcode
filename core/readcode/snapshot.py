"""``readcode snapshot``: materialize a git revision into blobs + tree.json."""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

import pathspec

from readcode import kbio
from readcode.schemas import validate

MAX_BYTES = 1024 * 1024
DEFAULT_EXCLUDE_DIRS = {"node_modules", "vendor", "dist", "build"}
DEFAULT_EXCLUDE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "poetry.lock", "go.sum"}
DEFAULT_EXCLUDE_GLOBS = ("*.min.*", "*.lock")

LANGUAGES = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "jsx", ".mjs": "javascript", ".go": "go", ".sql": "sql", ".java": "java",
    ".kt": "kotlin", ".rb": "ruby", ".php": "php", ".rs": "rust", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".swift": "swift", ".scala": "scala",
    ".sh": "shell", ".ps1": "powershell", ".lua": "lua", ".md": "markdown",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".html": "html", ".css": "css",
}


class SnapshotError(RuntimeError):
    pass


def _spec(lines: list[str]) -> pathspec.PathSpec:
    """Gitignore-style matcher; 'gitwildmatch' is the pre-1.0 pathspec name."""
    try:
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except KeyError:
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _git(repo: Path, *args: str, stdout_file: Path | None = None) -> str:
    cmd = ["git", "-C", str(repo), *args]
    try:
        if stdout_file is not None:
            with open(stdout_file, "wb") as fh:
                result = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)
            err = result.stderr.decode("utf-8", "replace")
            out = ""
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            err, out = result.stderr, result.stdout
    except OSError as exc:
        raise SnapshotError(f"Could not run git: {exc}") from exc
    if result.returncode != 0:
        raise SnapshotError(f"git {' '.join(args)} failed: {err.strip()}")
    return out.strip()


def detect_language(path: str) -> str | None:
    return LANGUAGES.get(PurePosixPath(path).suffix.lower())


def count_lines(data: bytes) -> int:
    if not data:
        return 0
    n = data.count(b"\n")
    return n if data.endswith(b"\n") else n + 1


def _safe_extract(tar_path: Path, dest: Path) -> list[str]:
    """Extract regular files only; reject absolute or '..' paths. Returns relative posix paths."""
    paths: list[str] = []
    root = dest.resolve()
    with tarfile.open(tar_path) as tar:
        for member in tar:
            if not member.isfile():
                continue  # directories, symlinks, pax headers, submodule stubs
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or member.name.startswith(("/", "\\")):
                raise SnapshotError(f"Unsafe path in archive: {member.name!r}")
            target = (dest / member.name).resolve()
            if root not in target.parents:
                raise SnapshotError(f"Unsafe path in archive: {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            assert src is not None
            with src, open(target, "wb") as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
            paths.append(member.name)
    return paths


def _default_excluded(path: str) -> bool:
    pure = PurePosixPath(path)
    if DEFAULT_EXCLUDE_DIRS.intersection(pure.parts[:-1]):
        return True
    if pure.name in DEFAULT_EXCLUDE_NAMES:
        return True
    return any(pure.match(g) for g in DEFAULT_EXCLUDE_GLOBS)


class _GitignoreMatcher:
    """Applies every .gitignore on the path from the repo root down (no cross-file negation)."""

    def __init__(self, root: Path, paths: list[str]):
        self._specs: dict[str, pathspec.PathSpec] = {}
        for p in paths:
            if PurePosixPath(p).name == ".gitignore":
                base = str(PurePosixPath(p).parent)
                lines = (root / p).read_text(encoding="utf-8", errors="replace").splitlines()
                self._specs["" if base == "." else base] = _spec(lines)

    def matches(self, path: str) -> bool:
        parts = PurePosixPath(path).parts
        for depth in range(len(parts)):
            spec = self._specs.get("/".join(parts[:depth]))
            if spec and spec.match_file("/".join(parts[depth:])):
                return True
        return False


def _sort_key(date: str) -> datetime:
    return datetime.fromisoformat(date.replace("Z", "+00:00"))


def snapshot_study(kb: Path, study: str, rev: str, repo_path: Path | None = None) -> dict:
    """Snapshot ``rev``; returns the study.json snapshot entry."""
    sdir = kbio.study_dir(kb, study)
    study_json = sdir / "study.json"
    if not study_json.is_file():
        raise SnapshotError(f"{study_json} not found; run `readcode init` first")
    study_data = kbio.read_json(study_json)

    if repo_path is None:
        local = study_data["repo"].get("localPath")
        if not local:
            raise SnapshotError(
                "The study has no repo.localPath (it was initialised from a URL); "
                "pass --repo-path <local checkout>"
            )
        repo_path = Path(local)
    repo_path = Path(repo_path)
    if not repo_path.is_dir():
        raise SnapshotError(f"Repo path is not a directory: {repo_path}")

    sha = _git(repo_path, "rev-parse", "--verify", f"{rev}^{{commit}}")
    date = _git(repo_path, "show", "-s", "--format=%cI", sha)
    message = _git(repo_path, "show", "-s", "--format=%s", sha)

    study_spec = _spec(study_data.get("exclude", []))
    files: list[dict] = []
    excluded: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="readcode-") as tmp:
        tmp_dir = Path(tmp)
        tar_path = tmp_dir / "archive.tar"
        _git(repo_path, "archive", "--format=tar", sha, stdout_file=tar_path)
        root = tmp_dir / "tree"
        root.mkdir()
        paths = sorted(_safe_extract(tar_path, root))
        tar_path.unlink()
        gitignore = _GitignoreMatcher(root, paths)

        for path in paths:
            if _default_excluded(path):
                excluded.append({"path": path, "reason": "default"})
                continue
            if gitignore.matches(path):
                excluded.append({"path": path, "reason": "gitignore"})
                continue
            if study_spec.match_file(path):
                excluded.append({"path": path, "reason": "study"})
                continue
            full = root / path
            if full.stat().st_size > MAX_BYTES:
                excluded.append({"path": path, "reason": "size"})
                continue
            data = full.read_bytes()
            if b"\x00" in data[:8192]:
                excluded.append({"path": path, "reason": "binary"})
                continue
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                excluded.append({"path": path, "reason": "binary"})  # not valid UTF-8 text
                continue
            digest = kbio.sha256_hex(data)
            blob = kbio.blob_path(sdir, digest)
            if not blob.exists():
                kbio.atomic_write_bytes(blob, data)
            files.append({
                "path": path,
                "blob": digest,
                "language": detect_language(path),
                "lines": count_lines(data),
                "bytes": len(data),
                "indexed": False,
            })

    tree = {"schemaVersion": 1, "sha": sha, "files": files, "excluded": excluded}
    errors = validate("tree", tree)
    if errors:
        raise SnapshotError("Invalid tree.json: " + "; ".join(errors))
    kbio.atomic_write_json(kbio.snapshot_dir(sdir, sha) / "tree.json", tree)

    entry = {"sha": sha, "date": date, "message": message, "status": "partial"}
    snapshots = [s for s in study_data["snapshots"] if s["sha"] != sha]
    snapshots.append(entry)
    snapshots.sort(key=lambda s: _sort_key(s["date"]))
    study_data["snapshots"] = snapshots
    errors = validate("study", study_data)
    if errors:
        raise SnapshotError("Invalid study.json: " + "; ".join(errors))
    kbio.atomic_write_json(study_json, study_data)
    return entry
