"""``readcode init``: create a study.json skeleton."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from readcode import kbio
from readcode.schemas import validate

_URL_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]+://|[\w.-]+@[\w.-]+:)")


_USERINFO_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]+://)[^/@]*@")


def strip_userinfo(url: str) -> str:
    """Drop credentials from scheme URLs (https://user:token@host/x -> https://host/x)."""
    return _USERINFO_RE.sub(lambda m: m.group(1), url)


class InitError(RuntimeError):
    pass


def _origin_url(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    url = result.stdout.strip()
    return url if result.returncode == 0 and url else None


def _repo_info(repo: str) -> dict:
    if _URL_RE.match(repo):
        return {"url": strip_userinfo(repo)}
    path = Path(repo).resolve()
    if not path.is_dir():
        raise InitError(f"--repo is neither a URL nor an existing directory: {repo}")
    return {"url": strip_userinfo(_origin_url(path) or str(path)), "localPath": str(path)}


def init_study(kb: Path, study: str, repo: str, title: str | None = None,
               language: str = "es", force: bool = False) -> Path:
    """Create ``<kb>/<study>/study.json``; returns its path."""
    study_json = kbio.study_dir(kb, study) / "study.json"
    if study_json.exists() and not force:
        raise InitError(f"{study_json} already exists (use --force to overwrite)")
    data = {
        "schemaVersion": 1,
        "name": study,
        "title": title or study,
        "repo": _repo_info(repo),
        "language": language,
        "exclude": [],
        "tools": {"graphify": False, "archify": False},
        "snapshots": [],
    }
    errors = validate("study", data)
    if errors:
        raise InitError("Invalid study: " + "; ".join(errors))
    kbio.atomic_write_json(study_json, data)
    return study_json
