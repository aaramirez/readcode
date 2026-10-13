"""Access to the study-format JSON Schemas (source of truth: repo-root ``schemas/``)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

KINDS = (
    "catalog",
    "study",
    "tree",
    "symbols",
    "explain",
    "dir",
    "tour",
    "changes",
    "diff-explain",
    "links",
    "issues",
)


class SchemaError(RuntimeError):
    """Raised when the schemas directory or a schema file is missing or unknown."""


def _read(name: str) -> dict:
    path = SCHEMAS_DIR / f"{name}.schema.json"
    if not path.is_file():
        raise SchemaError(
            f"Schema file not found: {path}. readcode v1 expects the repo-root "
            f"'schemas/' directory (editable install); packaging schemas is not supported yet."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(kind: str) -> dict:
    """Return the JSON Schema for ``kind`` (one of ``KINDS``)."""
    if kind not in KINDS:
        raise SchemaError(f"Unknown schema kind {kind!r}; expected one of: {', '.join(KINDS)}")
    return _read(kind)


@lru_cache(maxsize=1)
def _registry() -> Registry:
    registry = Registry()
    for name in ("common", *KINDS):
        schema = _read(name)
        registry = registry.with_resource(schema["$id"], Resource(schema, DRAFT202012))
    return registry


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(kind), registry=_registry())


def _json_path(error) -> str:
    out = "$"
    for part in error.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def validate(kind: str, data: object) -> list[str]:
    """Validate ``data`` against the ``kind`` schema.

    Returns human-readable errors as ``"<json path>: <message>"``; empty if valid.
    """
    errors = sorted(_validator(kind).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{_json_path(e)}: {e.message}" for e in errors]
