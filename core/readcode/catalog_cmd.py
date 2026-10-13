"""`readcode catalog`: regenerate <kb>/catalog.json from the studies in a kb directory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from readcode import kbio
from readcode.schemas import validate


class CatalogError(RuntimeError):
    """The kb directory does not exist."""


def _latest_mtime(sdir: Path) -> float:
    return max((p.stat().st_mtime for p in sdir.rglob("*") if p.is_file()), default=0.0)


def build_catalog(kb: Path | str) -> tuple[dict, list[str]]:
    """Write <kb>/catalog.json; return (catalog, warnings about skipped studies)."""
    kb = Path(kb)
    if not kb.is_dir():
        raise CatalogError(f"{kb} is not a directory")
    studies, warnings = [], []
    for sdir in sorted((p for p in kb.iterdir() if (p / "study.json").is_file()),
                       key=lambda p: p.name):
        try:
            data = json.loads((sdir / "study.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(f"{sdir.name}: study.json ilegible ({exc}); omitido")
            continue
        errors = validate("study", data)
        if errors:
            warnings.append(f"{sdir.name}: study.json inválido ({errors[0]}); omitido")
            continue
        updated = datetime.fromtimestamp(_latest_mtime(sdir), tz=timezone.utc)
        entry = {"name": sdir.name, "title": data["title"], "repo": data["repo"],
                 "snapshots": len(data["snapshots"]),
                 "updated": updated.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if validate("catalog", {"schemaVersion": 1, "studies": [entry]}):
            warnings.append(f"{sdir.name}: nombre de directorio no válido para un estudio; omitido")
            continue
        studies.append(entry)
    catalog = {"schemaVersion": 1, "studies": studies}
    kbio.atomic_write_json(kb / "catalog.json", catalog)
    return catalog, warnings
