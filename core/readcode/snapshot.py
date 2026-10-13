"""``readcode snapshot``: materialize a git revision into blobs + tree.json.

Blob bytes come straight from the git object database (``ls-tree`` + ``cat-file``), so they
are never affected by core.autocrlf, .gitattributes or filters: the same commit yields the
same blob hashes on every machine.
"""

from __future__ import annotations

import subprocess
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


def _run_git(repo: Path, *args: str) -> bytes:
    cmd = ["git", "-C", str(repo), *args]
    try:
        result = subprocess.run(cmd, capture_output=True)
    except OSError as exc:
        raise SnapshotError(f"Could not run git: {exc}") from exc
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"git {' '.join(args)} failed: {err}")
    return result.stdout


def _git(repo: Path, *args: str) -> str:
    return _run_git(repo, *args).decode("utf-8").strip()


def detect_language(path: str) -> str | None:
    return LANGUAGES.get(PurePosixPath(path).suffix.lower())


def count_lines(data: bytes) -> int:
    if not data:
        return 0
    n = data.count(b"\n")
    return n if data.endswith(b"\n") else n + 1


def _list_blobs(repo: Path, sha: str) -> list[tuple[str, str, int]]:
    """(path, blob oid, size) for regular files; submodules and symlinks are skipped."""
    out = _run_git(repo, "ls-tree", "-r", "-l", "-z", "--full-tree", sha)
    entries = []
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, raw_path = rec.partition(b"\t")
        mode, otype, oid, size = meta.decode("ascii").split()
        if otype != "blob" or mode == "120000":
            continue
        entries.append((raw_path.decode("utf-8", "replace"), oid, int(size)))
    return sorted(entries)


class _BlobReader:
    """Raw blob bytes via one `git cat-file --batch` process (no eol/filter conversion)."""

    def __init__(self, repo: Path):
        try:
            self._proc = subprocess.Popen(
                ["git", "-C", str(repo), "cat-file", "--batch"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise SnapshotError(f"Could not run git: {exc}") from exc

    def read(self, oid: str) -> bytes:
        proc = self._proc
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(oid.encode("ascii") + b"\n")
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        if len(header) != 3 or header[1] != b"blob":
            raise SnapshotError(f"git cat-file could not read blob {oid}")
        size = int(header[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)  # trailing newline
        if len(data) != size:
            raise SnapshotError(f"Short read for blob {oid}")
        return data

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        if self._proc.stdout:
            self._proc.stdout.close()
        self._proc.wait()


def _default_excluded(path: str) -> bool:
    pure = PurePosixPath(path)
    if DEFAULT_EXCLUDE_DIRS.intersection(pure.parts[:-1]):
        return True
    if pure.name in DEFAULT_EXCLUDE_NAMES:
        return True
    return any(pure.match(g) for g in DEFAULT_EXCLUDE_GLOBS)


class _GitignoreMatcher:
    """Applies every .gitignore on the path from the repo root down (no cross-file negation)."""

    def __init__(self, gitignores: dict[str, bytes]):
        """``gitignores`` maps a directory ("" for root) to its .gitignore bytes."""
        self._specs = {
            base: _spec(raw.decode("utf-8", "replace").splitlines())
            for base, raw in gitignores.items()
        }

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

    sha = _git(repo_path, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
    date = _git(repo_path, "show", "-s", "--format=%cI", sha)
    message = _git(repo_path, "show", "-s", "--format=%s", sha)

    study_spec = _spec(study_data.get("exclude", []))
    files: list[dict] = []
    excluded: list[dict] = []

    entries = _list_blobs(repo_path, sha)
    reader = _BlobReader(repo_path)
    try:
        gitignores: dict[str, bytes] = {}
        for path, oid, size in entries:
            if PurePosixPath(path).name == ".gitignore" and size <= MAX_BYTES:
                parent = str(PurePosixPath(path).parent)
                gitignores["" if parent == "." else parent] = reader.read(oid)
        gitignore = _GitignoreMatcher(gitignores)

        for path, oid, size in entries:
            if _default_excluded(path):
                excluded.append({"path": path, "reason": "default"})
                continue
            if gitignore.matches(path):
                excluded.append({"path": path, "reason": "gitignore"})
                continue
            if study_spec.match_file(path):
                excluded.append({"path": path, "reason": "study"})
                continue
            if size > MAX_BYTES:
                excluded.append({"path": path, "reason": "size"})
                continue
            data = reader.read(oid)
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
    finally:
        reader.close()

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
