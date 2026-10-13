"""Marker grammar parity: schemas/marker-vectors.json is also consumed by the
viewer's vitest (viewer/src/lib/markers.test.ts), so the Python and TypeScript
parsers cannot drift."""

import json
from pathlib import Path

import pytest

from readcode.refs import parse_markers

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "marker-vectors.json").read_text(encoding="utf-8"))


def _as_dict(m) -> dict:
    return {"kind": m.kind, "raw": m.raw, "path": m.path, "symbol": m.symbol,
            "range": list(m.range) if m.range is not None else None, "label": m.label}


def test_vectors_present():
    assert len(VECTORS) >= 30
    assert all({"name", "input", "expected"} <= set(v) for v in VECTORS)


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_marker_vector(vector):
    assert [_as_dict(m) for m in parse_markers(vector["input"])] == vector["expected"]
