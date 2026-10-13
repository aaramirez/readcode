"""``readcode diff``: file-level and line-level changes between two studied snapshots."""

from __future__ import annotations

import difflib
from pathlib import Path

from readcode import kbio
from readcode.schemas import validate

MERGE_GAP = 3


class DiffError(RuntimeError):
    pass


def _normalize_eol(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _range(start: int, end: int) -> list[int] | None:
    return [start + 1, end] if end > start else None


def compute_hunks(old: list[str], new: list[str]) -> list[dict]:
    ops = [op for op in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
           if op[0] != "equal"]
    groups: list[list[int]] = []  # [i1, i2, j1, j2]
    for _, i1, i2, j1, j2 in ops:
        if groups and i1 - groups[-1][1] < MERGE_GAP:
            groups[-1][1], groups[-1][3] = i2, j2
        else:
            groups.append([i1, i2, j1, j2])
    return [
        {
            "fromRange": _range(i1, i2),
            "toRange": _range(j1, j2),
            "header": f"@@ -{i1 + 1},{i2 - i1} +{j1 + 1},{j2 - j1} @@",
        }
        for i1, i2, j1, j2 in groups
    ]


def diff_snapshots(kb: Path | str, study: str, sha_a: str, sha_b: str) -> dict:
    sdir = kbio.study_dir(kb, study)
    study_json = sdir / "study.json"
    if not study_json.is_file():
        raise DiffError(f"{study_json} not found; run `readcode init` first")
    study_data = kbio.read_json(study_json)
    try:
        a = kbio.resolve_sha(study_data, sha_a, sdir)
        b = kbio.resolve_sha(study_data, sha_b, sdir)
    except ValueError as exc:
        raise DiffError(str(exc)) from exc

    def files_of(sha: str) -> dict[str, dict]:
        path = kbio.snapshot_dir(sdir, sha) / "tree.json"
        if not path.is_file():
            raise DiffError(f"{path} not found; run `readcode snapshot` first")
        return {f["path"]: f for f in kbio.read_json(path)["files"]}

    old, new = files_of(a), files_of(b)
    added = {p: f for p, f in new.items() if p not in old}
    deleted = {p: f for p, f in old.items() if p not in new}

    changes: list[dict] = []
    renamed_old: set[str] = set()
    for p, f in sorted(added.items()):
        match = next((q for q, g in sorted(deleted.items())
                      if g["blob"] == f["blob"] and q not in renamed_old), None)
        if match:
            renamed_old.add(match)
            changes.append({"path": p, "status": "renamed", "oldPath": match,
                            "fromBlob": f["blob"], "toBlob": f["blob"], "hunks": []})
        else:
            changes.append({"path": p, "status": "added", "toBlob": f["blob"], "hunks": []})
    for p, f in sorted(deleted.items()):
        if p not in renamed_old:
            changes.append({"path": p, "status": "deleted", "fromBlob": f["blob"], "hunks": []})
    for p, f in sorted(new.items()):
        if p in old and old[p]["blob"] != f["blob"]:
            old_bytes = kbio.blob_path(sdir, old[p]["blob"]).read_bytes()
            new_bytes = kbio.blob_path(sdir, f["blob"]).read_bytes()
            entry = {"path": p, "status": "modified", "fromBlob": old[p]["blob"],
                     "toBlob": f["blob"]}
            if _normalize_eol(old_bytes) == _normalize_eol(new_bytes):
                entry.update(hunks=[], eolOnly=True)
            else:
                entry["hunks"] = compute_hunks(kbio.blob_lines(old_bytes),
                                               kbio.blob_lines(new_bytes))
            changes.append(entry)
    changes.sort(key=lambda c: c["path"])

    doc = {"schemaVersion": 1, "from": a, "to": b, "files": changes}
    errors = validate("changes", doc)
    if errors:
        raise DiffError("Invalid changes.json: " + "; ".join(errors))
    kbio.atomic_write_json(sdir / "diffs" / f"{a}..{b}" / "changes.json", doc)
    return doc
