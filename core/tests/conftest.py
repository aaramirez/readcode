import sys
from pathlib import Path

import pytest

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
sys.path.insert(0, str(_EXAMPLES))

from make_fixture import build_fixture  # noqa: E402


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory):
    """Builds the fixture repo once per session. Returns (path, sha1, sha2)."""
    path = tmp_path_factory.mktemp("fixture") / "repo"
    sha1, sha2 = build_fixture(path)
    return path, sha1, sha2
