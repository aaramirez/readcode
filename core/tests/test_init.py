import subprocess

from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.schemas import validate

runner = CliRunner()


def test_init_local_repo(tmp_path, fixture_repo):
    repo, _, _ = fixture_repo
    r = runner.invoke(app, ["init", str(tmp_path), "demo", "--repo", str(repo), "--title", "Demo"])
    assert r.exit_code == 0, r.output
    data = kbio.read_json(tmp_path / "demo" / "study.json")
    assert validate("study", data) == []
    assert data["title"] == "Demo" and data["language"] == "es"
    assert data["tools"] == {"graphify": False, "archify": False}
    assert data["snapshots"] == [] and data["exclude"] == []
    assert data["repo"]["localPath"] == str(repo.resolve())
    assert data["repo"]["url"] == str(repo.resolve())  # fixture has no origin


def test_init_uses_origin_url(tmp_path, fixture_repo):
    repo, _, _ = fixture_repo
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True)
    runner.invoke(app, ["init", str(tmp_path), "c", "--repo", str(clone)])
    data = kbio.read_json(tmp_path / "c" / "study.json")
    assert data["repo"]["url"] == str(repo)
    assert data["repo"]["localPath"] == str(clone.resolve())


def test_init_url_has_no_local_path(tmp_path):
    r = runner.invoke(app, ["init", str(tmp_path), "u", "--repo", "https://github.com/x/y.git"])
    assert r.exit_code == 0, r.output
    data = kbio.read_json(tmp_path / "u" / "study.json")
    assert data["repo"] == {"url": "https://github.com/x/y.git"}
    assert data["title"] == "u"


def test_init_refuses_overwrite_unless_force(tmp_path):
    args = ["init", str(tmp_path), "s", "--repo", "https://example.com/r.git"]
    assert runner.invoke(app, args).exit_code == 0
    r = runner.invoke(app, args)
    assert r.exit_code != 0 and "already exists" in r.output
    assert runner.invoke(app, [*args, "--force", "--language", "en"]).exit_code == 0
    assert kbio.read_json(tmp_path / "s" / "study.json")["language"] == "en"


def test_init_bad_inputs(tmp_path):
    r = runner.invoke(app, ["init", str(tmp_path), "s", "--repo", str(tmp_path / "nope")])
    assert r.exit_code != 0
    r = runner.invoke(app, ["init", str(tmp_path), "Bad Name", "--repo", "https://e.com/r"])
    assert r.exit_code != 0
