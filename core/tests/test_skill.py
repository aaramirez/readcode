"""The /readcode Claude Code skill: SKILL.md, prompts, helper scripts and install-skill."""

import importlib.util
import json
import re
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from readcode.cli import app
from readcode.install_skill import install_skill, skill_source

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "readcode"
EXAMPLE_KB = ROOT / "examples" / "kb"
SHA1 = "b42f63fb2414b4d4d830af722a64255504a80ee8"
SHA2 = "074ec965eabffb43a0224ef9f1426515d2818975"
PROMPTS = ["explain-file.md", "dir.md", "overview.md", "tour.md", "diff.md"]

runner = CliRunner()


def _script(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _docs():
    return [SKILL / "SKILL.md"] + [SKILL / "prompts" / p for p in PROMPTS]


# ------------------------------------------------------------------ SKILL.md / prompts


def test_skill_frontmatter_is_valid_yaml():
    yaml = pytest.importorskip("yaml")
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
    assert {"init", "snapshot", "index", "graph", "plan", "diff", "validate", "catalog"} <= seen


def test_prompts_and_scripts_referenced_by_skill_exist():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for name in set(re.findall(r"`([a-z-]+\.md)`", text)) - {"SKILL.md", "overview.md"}:
        assert (SKILL / "prompts" / name).is_file(), name
    for name in re.findall(r"scripts/([a-z_]+\.py)", text):
        assert (SKILL / "scripts" / name).is_file(), name


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


# ------------------------------------------------------------------ helper scripts


def test_file_context_on_example_snapshot():
    out = _script("file_context").file_context(
        EXAMPLE_KB / "fixture" / "snapshots" / SHA2, ["app/services/billing.py", "missing.py"])
    billing, missing = out
    assert billing["lines"] == 15
    assert Path(billing["blobFile"]).is_file()
    assert billing["blobHash"] in billing["blobFile"]
    assert "refund (function) L13-15" in billing["defs"]
    assert billing["importedBy"] == ["app/main.py", "app/services/refunds.py"]
    assert billing["usedBy"]["app/services/refunds.py"] == ["refund"]
    assert billing["explanation"] == "current"
    assert missing == {"path": "missing.py", "error": "not in tree.json"}


def test_stale_refs_on_example_update():
    out = _script("stale_refs").stale_refs(EXAMPLE_KB, "fixture", SHA1[:7], SHA2[:7])
    assert (out["from"], out["to"]) == (SHA1, SHA2)
    # only definitions whose text changed; compute_total/process are untouched
    assert out["changedSymbols"] == {
        "app/services/billing.py": ["refund"],
        "app/services/refunds.py": ["process_refund"],
        "web/src/api.ts": ["refundInvoice"],
    }
    explain = {e["path"]: e for e in out["explain"]}
    assert "app/services/billing.py" not in explain  # changed files are re-explained, not refreshed
    assert explain["app/models.py"]["markers"] == [
        "app/services/billing.py#refund", "app/services/refunds.py#process_refund"]
    tours = {t["id"]: t for t in out["tours"]}
    assert tours["flujo-facturacion"]["steps"] == [3, 6, 7]
    assert "worker-cola" not in tours


def test_stale_refs_flags_code_references(tmp_path):
    import shutil

    kb = tmp_path / "kb"
    shutil.copytree(EXAMPLE_KB / "fixture", kb / "fixture")
    # main.py calls billing.process; pretend process changed in the new snapshot.
    snap2 = kb / "fixture" / "snapshots" / SHA2
    syms = json.loads((snap2 / "symbols.json").read_text(encoding="utf-8"))
    for d in syms["files"]["app/services/billing.py"]["defs"]:
        if d["name"] == "process":
            d["range"] = [7, 10]  # different text than in the old snapshot
    (snap2 / "symbols.json").write_text(json.dumps(syms), encoding="utf-8")
    out = _script("stale_refs").stale_refs(kb, "fixture", SHA1, SHA2)
    assert "process" in out["changedSymbols"]["app/services/billing.py"]
    main = next(e for e in out["explain"] if e["path"] == "app/main.py")
    assert main["symbols"] == ["process"]


# ------------------------------------------------------------------ install-skill


def test_skill_source_is_repo_skill():
    assert skill_source() == SKILL.resolve()


def test_install_skill_copies_and_needs_force(tmp_path):
    dest = install_skill(tmp_path)
    assert dest == tmp_path / "readcode"
    assert (dest / "SKILL.md").read_bytes() == (SKILL / "SKILL.md").read_bytes()
    for p in PROMPTS:
        assert (dest / "prompts" / p).is_file()
    assert (dest / "scripts" / "stale_refs.py").is_file()
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
