import subprocess

import pytest
from typer.testing import CliRunner

from readcode import kbio
from readcode.cli import app
from readcode.schemas import validate
from readcode.snapshot import count_lines, detect_language

runner = CliRunner()


@pytest.fixture()
def study(tmp_path, fixture_repo):
    repo, sha1, sha2 = fixture_repo
    r = runner.invoke(app, ["init", str(tmp_path), "demo", "--repo", str(repo)])
    assert r.exit_code == 0, r.output
    return tmp_path, tmp_path / "demo", sha1, sha2


def snap(kb, rev, *extra, name="demo"):
    r = runner.invoke(app, ["snapshot", str(kb), name, "--sha", rev, *extra])
    assert r.exit_code == 0, r.output
    return r


def tree_of(sd, sha):
    return kbio.read_json(sd / "snapshots" / sha / "tree.json")


def test_snapshot_both_commits(study, fixture_repo):
    kb, sd, sha1, sha2 = study
    repo = fixture_repo[0]
    snap(kb, sha2)
    snap(kb, sha1)  # out of order on purpose
    t1, t2 = tree_of(sd, sha1), tree_of(sd, sha2)
    for t in (t1, t2):
        assert validate("tree", t) == []
        paths = [f["path"] for f in t["files"]]
        assert paths == sorted(paths)
    reasons = {e["path"]: e["reason"] for e in t1["excluded"]}
    assert reasons["node_modules/junk.js"] == "default"
    assert reasons["package-lock.json"] == "default"
    assert reasons["assets/logo.bin"] == "binary"
    assert "node_modules/junk.js" not in [f["path"] for f in t1["files"]]

    p1 = {f["path"]: f for f in t1["files"]}
    p2 = {f["path"]: f for f in t2["files"]}
    assert "db/queries.sql" in p1 and "db/queries.sql" not in p2
    assert "app/services/refunds.py" in p2 and "app/services/refunds.py" not in p1
    assert p1["app/models.py"]["blob"] == p2["app/models.py"]["blob"]
    assert p1["app/services/billing.py"]["blob"] != p2["app/services/billing.py"]["blob"]
    assert p1["app/models.py"]["language"] == "python"
    assert p1["db/schema.sql"]["language"] == "sql"
    assert p1[".gitignore"]["language"] is None

    blobs = {p.stem for p in (sd / "blobs").rglob("*.txt")}
    assert len(blobs) < len(t1["files"]) + len(t2["files"])
    assert blobs == {f["blob"] for f in [*t1["files"], *t2["files"]]}

    f = p1["app/models.py"]
    content = kbio.blob_path(sd, f["blob"]).read_bytes()
    assert content == (repo / "app/models.py").read_bytes()
    assert kbio.sha256_hex(content) == f["blob"]
    assert f["bytes"] == len(content)

    data = kbio.read_json(sd / "study.json")
    assert validate("study", data) == []
    assert [s["sha"] for s in data["snapshots"]] == [sha1, sha2]  # sorted by date
    assert data["snapshots"][0]["message"] == "initial"
    assert data["snapshots"][0]["status"] == "partial"
    assert data["snapshots"][1]["date"].startswith("2026-01-11T10:00:00")


def test_idempotent_and_short_rev(study):
    kb, sd, sha1, sha2 = study
    snap(kb, sha1[:10])
    snap(kb, sha2)
    snap(kb, sha1)
    before = {p: p.read_bytes() for p in sd.rglob("*") if p.is_file()}
    snap(kb, "main")  # resolves to sha2
    snap(kb, sha1)
    after = {p: p.read_bytes() for p in sd.rglob("*") if p.is_file()}
    assert after == before
    assert len(kbio.read_json(sd / "study.json")["snapshots"]) == 2


def test_study_exclude(study):
    kb, sd, sha1, _ = study
    data = kbio.read_json(sd / "study.json")
    data["exclude"] = ["web/", "*.sql"]
    kbio.atomic_write_json(sd / "study.json", data)
    snap(kb, sha1)
    reasons = {e["path"]: e["reason"] for e in tree_of(sd, sha1)["excluded"]}
    assert reasons["web/src/api.ts"] == "study"
    assert reasons["db/schema.sql"] == "study"


def test_gitignore_and_size_rules(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    env = ["-c", "user.name=t", "-c", "user.email=t@e.com", "-c", "commit.gpgsign=false"]

    def git(*a):
        subprocess.run(["git", *env, "-C", str(repo), *a], check=True, capture_output=True)

    git("init", "-q")
    git("config", "core.autocrlf", "false")
    (repo / ".gitignore").write_text("*.tmp\n/secret/\n")
    (repo / "sub").mkdir()
    (repo / "sub" / ".gitignore").write_text("local.txt\n")
    (repo / "sub" / "local.txt").write_text("x")
    (repo / "keep.tmp").write_text("x")
    (repo / "secret").mkdir()
    (repo / "secret" / "a.py").write_text("x")
    (repo / "big.txt").write_bytes(b"a" * (1024 * 1024 + 1))
    (repo / "ok.min.js").write_text("x")
    (repo / "vendor").mkdir()
    (repo / "vendor" / "v.go").write_text("x")
    (repo / "latin.txt").write_bytes(b"caf\xe9\n")
    (repo / "ok.py").write_bytes(b"a\nb")
    git("add", "-A", "-f")
    git("commit", "-q", "-m", "m")
    kb = tmp_path / "kb"
    assert runner.invoke(app, ["init", str(kb), "s", "--repo", str(repo)]).exit_code == 0
    snap(kb, "HEAD", name="s")
    sha = kbio.read_json(kb / "s" / "study.json")["snapshots"][0]["sha"]
    t = tree_of(kb / "s", sha)
    assert {e["path"]: e["reason"] for e in t["excluded"]} == {
        "keep.tmp": "gitignore",
        "secret/a.py": "gitignore",
        "sub/local.txt": "gitignore",
        "big.txt": "size",
        "ok.min.js": "default",
        "vendor/v.go": "default",
        "latin.txt": "binary",
    }
    ok = next(f for f in t["files"] if f["path"] == "ok.py")
    assert ok["lines"] == 2 and ok["bytes"] == 3


def test_url_study_requires_repo_path(tmp_path, fixture_repo):
    repo, sha1, _ = fixture_repo
    runner.invoke(app, ["init", str(tmp_path), "demo", "--repo", "https://example.com/r.git"])
    r = runner.invoke(app, ["snapshot", str(tmp_path), "demo", "--sha", sha1])
    assert r.exit_code != 0 and "--repo-path" in r.output
    snap(tmp_path, sha1, "--repo-path", str(repo))


def test_errors(study):
    kb, _, _, _ = study
    r = runner.invoke(app, ["snapshot", str(kb), "demo", "--sha", "nonexistent-rev"])
    assert r.exit_code != 0 and "error" in r.output
    r = runner.invoke(app, ["snapshot", str(kb), "missing", "--sha", "HEAD"])
    assert r.exit_code != 0


def test_helpers():
    assert count_lines(b"") == 0 and count_lines(b"a\n") == 1 and count_lines(b"a\nb") == 2
    assert detect_language("x/y.TSX") == "tsx" and detect_language("Makefile") is None


def test_blobs_are_raw_despite_eol_conversion(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    env = ["-c", "user.name=t", "-c", "user.email=t@e.com", "-c", "commit.gpgsign=false"]

    def git(*a):
        return subprocess.run(["git", *env, "-C", str(repo), *a], check=True, capture_output=True).stdout

    git("init", "-q")
    git("config", "core.autocrlf", "false")
    (repo / "a.txt").write_bytes(b"one\ntwo\n")
    git("add", "a.txt")
    git("commit", "-q", "-m", "m")
    git("config", "core.autocrlf", "true")
    (repo / ".gitattributes").write_text("* text eol=crlf\n")
    kb = tmp_path / "kb"
    assert runner.invoke(app, ["init", str(kb), "s", "--repo", str(repo)]).exit_code == 0
    snap(kb, "HEAD", name="s")
    sha = kbio.read_json(kb / "s" / "study.json")["snapshots"][0]["sha"]
    entry = next(f for f in tree_of(kb / "s", sha)["files"] if f["path"] == "a.txt")
    stored = kbio.blob_path(kb / "s", entry["blob"]).read_bytes()
    assert stored == git("cat-file", "blob", f"{sha}:a.txt") == b"one\ntwo\n"


def test_rev_cannot_be_an_option(study):
    kb, _, _, _ = study
    r = runner.invoke(app, ["snapshot", str(kb), "demo", "--sha", "--output=x"])
    assert r.exit_code != 0
