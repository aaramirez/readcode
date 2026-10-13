import json
from pathlib import Path

import pytest

from readcode import schemas

DATA = Path(__file__).parent / "data" / "schemas"


def _cases(sub: str):
    return [
        pytest.param(kind_dir.name, f, id=f"{kind_dir.name}/{f.name}")
        for kind_dir in sorted(DATA.iterdir())
        for f in sorted((kind_dir / sub).glob("*.json"))
    ]


@pytest.mark.parametrize("kind,path", _cases("valid"))
def test_valid_examples_pass(kind, path):
    assert schemas.validate(kind, json.loads(path.read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("kind,path", _cases("invalid"))
def test_invalid_examples_fail(kind, path):
    errors = schemas.validate(kind, json.loads(path.read_text(encoding="utf-8")))
    assert errors
    assert all(e.startswith("$") for e in errors)


def test_every_kind_has_examples():
    for kind in schemas.KINDS:
        assert list((DATA / kind / "valid").glob("*.json")), kind
        assert len(list((DATA / kind / "invalid").glob("*.json"))) >= 2, kind


def test_error_message_has_json_path():
    data = json.loads((DATA / "study" / "valid" / "full.json").read_text(encoding="utf-8"))
    data["snapshots"][0]["sha"] = "abc"
    (err,) = schemas.validate("study", data)
    assert err.startswith("$.snapshots[0].sha:")


def test_every_property_has_description():
    def walk(node, where):
        if isinstance(node, dict):
            for key, sub in node.get("properties", {}).items():
                assert "description" in sub or "$ref" in sub, f"{where}.{key}"
                walk(sub, f"{where}.{key}")
            for key in ("items", "additionalProperties"):
                if isinstance(node.get(key), dict):
                    walk(node[key], f"{where}.{key}")

    for kind in schemas.KINDS:
        walk(schemas.load_schema(kind), kind)


def test_unknown_kind():
    with pytest.raises(schemas.SchemaError):
        schemas.load_schema("nope")


def test_missing_schemas_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(schemas, "SCHEMAS_DIR", tmp_path)
    with pytest.raises(schemas.SchemaError, match="not found"):
        schemas.load_schema("study")
