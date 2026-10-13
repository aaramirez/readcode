import pytest

from readcode import kbio
from readcode.archify_cmd import ArchifyError, _find_snapshot_dir

SHA = "074ec965eabffb43a0224ef9f1426515d2818975"


@pytest.fixture()
def sdir(tmp_path):
    sd = tmp_path / "kb" / "demo"
    kbio.atomic_write_json(sd / "study.json", {"snapshots": [{"sha": SHA}]})
    (sd / "snapshots" / SHA).mkdir(parents=True)
    return sd


def test_full_sha_and_unique_prefix(sdir):
    assert _find_snapshot_dir(sdir, SHA) == sdir / "snapshots" / SHA
    assert _find_snapshot_dir(sdir, SHA[:7]) == sdir / "snapshots" / SHA


@pytest.mark.parametrize("bad", ["..", "../..", "", "ffff"])
def test_rejects_unstudied_or_traversal(sdir, bad):
    with pytest.raises(ArchifyError):
        _find_snapshot_dir(sdir, bad)


def test_study_json_traversal_sha_is_ignored(tmp_path, sdir):
    victim = tmp_path / "victim"
    victim.mkdir()
    kbio.atomic_write_json(sdir / "study.json", {"snapshots": [{"sha": str(victim)}]})
    with pytest.raises(ArchifyError):
        _find_snapshot_dir(sdir, str(victim))
