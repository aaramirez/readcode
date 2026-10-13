"""``readcode install-skill``: copy the Claude Code skill (skills/readcode) to a skills directory."""

from __future__ import annotations

import shutil
from pathlib import Path


class InstallSkillError(RuntimeError):
    pass


def skill_source() -> Path:
    """skills/readcode of the readcode checkout this package runs from (editable install)."""
    src = Path(__file__).resolve().parents[2] / "skills" / "readcode"
    if not (src / "SKILL.md").is_file():
        raise InstallSkillError(
            f"skill sources not found at {src}; install readcode from a checkout "
            "(pip install -e core) or copy skills/readcode by hand"
        )
    return src


def default_dest() -> Path:
    return Path.home() / ".claude" / "skills"


def install_skill(dest: Path | str | None = None, force: bool = False,
                  src: Path | str | None = None) -> Path:
    """Copy the skill to ``<dest>/readcode``; returns that path.

    Refuses to overwrite an existing installation unless ``force`` (then it is replaced).
    """
    source = Path(src) if src is not None else skill_source()
    target = Path(dest if dest is not None else default_dest()).expanduser() / "readcode"
    if target.exists():
        if not force:
            raise InstallSkillError(f"{target} already exists (use --force to overwrite)")
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return target
