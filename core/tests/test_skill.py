"""The /readcode Claude Code skill: SKILL.md, prompts and install-skill."""

import json
import re
from pathlib import Path

import pytest
import typer.main
import yaml
from typer.testing import CliRunner

from readcode.cli import app
from readcode.install_skill import install_skill, skill_source

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "readcode"
EXAMPLE_KB = ROOT / "examples" / "kb"
SHA2 = "074ec965eabffb43a0224ef9f1426515d2818975"
PROMPTS = ["explain-file.md", "dir.md", "overview.md", "tour.md", "diff.md"]

runner = CliRunner()


def _docs():
    return [SKILL / "SKILL.md"] + [SKILL / "prompts" / p for p in PROMPTS]


# ------------------------------------------------------------------ SKILL.md / prompts


def test_skill_frontmatter_is_valid_yaml():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with a --- frontmatter block"
    meta = yaml.safe_load(m.group(1))
    assert meta["name"] == "readcode"
    desc = meta["description"]
    for trigger in ("/readcode", "estudia este repo", "actualiza el estudio",
                    "explica los cambios entre commits", "agrega un tour"):
        assert trigger in desc


def test_prompt_templates_exist_and_have_language_placeholder():
    for p in PROMPTS:
        text = (SKILL / "prompts" / p).read_text(encoding="utf-8")
        assert "{{LANGUAGE}}" in text, p
        assert "[[ref:" in text and "[[archify:" in text, p


def test_every_cli_command_mentioned_exists():
    registered = {c.name for c in typer.main.get_command(app).commands.values()}
    # `readcode <cmd>` at the start of a (code) line or right after a backtick.
    pattern = re.compile(r"(?m)(?:^[ \t]*|`)readcode[ \t]+([a-z][a-z-]*)")
    seen = set()
    for doc in _docs():
        for cmd in pattern.findall(doc.read_text(encoding="utf-8")):
            assert cmd in registered, f"{doc.name}: `readcode {cmd}` is not a CLI command"
            seen.add(cmd)
    assert {"init", "snapshot", "index", "graph", "plan", "diff", "validate", "catalog",
            "context", "stale", "mark"} <= seen


def test_prompts_referenced_by_skill_exist():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    names = set(re.findall(r"`([a-z-]+\.md)`", text)) - {"SKILL.md"}
    assert set(PROMPTS) <= names
    for name in names:
        assert (SKILL / "prompts" / name).is_file(), name
    for doc in _docs():  # helpers are CLI commands now, not skill scripts
        assert "scripts/" not in doc.read_text(encoding="utf-8"), doc.name


def test_prompt_examples_quote_the_reference_study():
    """JSON examples marked as real must match the files they quote (no drift)."""
    snap = EXAMPLE_KB / "fixture" / "snapshots" / SHA2
    real = json.loads((snap / "explain" / "app" / "services" / "billing.py.json")
                      .read_text(encoding="utf-8"))
    text = (SKILL / "prompts" / "explain-file.md").read_text(encoding="utf-8")
    assert real["blobHash"] in text
    assert json.dumps(real["summary"], ensure_ascii=False) in text
    dirs = json.loads((snap / "dirs" / "app" / "services.json").read_text(encoding="utf-8"))
    assert json.dumps(dirs["summary"], ensure_ascii=False) in (
        SKILL / "prompts" / "dir.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ install-skill


def test_skill_source_is_repo_skill():
    assert skill_source() == SKILL.resolve()


def test_install_skill_copies_and_needs_force(tmp_path):
    dest = install_skill(tmp_path)
    assert dest == tmp_path / "readcode"
    assert (dest / "SKILL.md").read_bytes() == (SKILL / "SKILL.md").read_bytes()
    for p in PROMPTS:
        assert (dest / "prompts" / p).is_file()
    assert not list(dest.rglob("__pycache__"))

    (dest / "stale.txt").write_text("x")
    with pytest.raises(RuntimeError, match="--force"):
        install_skill(tmp_path)
    install_skill(tmp_path, force=True)
    assert not (dest / "stale.txt").exists()


def test_install_skill_cli(tmp_path):
    result = runner.invoke(app, ["install-skill", "--dest", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert str(tmp_path / "readcode") in result.stdout
    assert (tmp_path / "readcode" / "SKILL.md").is_file()

    again = runner.invoke(app, ["install-skill", "--dest", str(tmp_path)])
    assert again.exit_code == 1
    assert "--force" in again.output

    forced = runner.invoke(app, ["install-skill", "--dest", str(tmp_path), "--force"])
    assert forced.exit_code == 0, forced.output
