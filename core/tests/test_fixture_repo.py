import subprocess

from make_fixture import build_fixture


def git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=path, check=True, capture_output=True, text=True
    ).stdout


def test_two_commits(fixture_repo):
    path, sha1, sha2 = fixture_repo
    log = git(path, "log", "--format=%H %s").splitlines()
    assert log == [f"{sha2} feature: refunds", f"{sha1} initial"]


def test_second_commit_changes(fixture_repo):
    path, sha1, sha2 = fixture_repo
    out = git(path, "diff", "--name-status", sha1, sha2).splitlines()
    assert sorted(out) == [
        "A\tapp/services/refunds.py",
        "D\tdb/queries.sql",
        "M\tapp/services/billing.py",
        "M\tweb/src/api.ts",
    ]


def test_binary_file_has_nul(fixture_repo):
    path, _, _ = fixture_repo
    assert b"\x00" in (path / "assets" / "logo.bin").read_bytes()


def test_shas_stable_across_builds(fixture_repo, tmp_path):
    _, sha1, sha2 = fixture_repo
    assert build_fixture(tmp_path / "again") == (sha1, sha2)
