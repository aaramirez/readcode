"""``readcode migrate``: rewrite v1 study files to the current format.

Today that is one thing: the root directory summary moves from ``dirs/_root.json`` to
``dir-root.json`` (only when tree.json has no directory named ``_root``, where
``dirs/_root.json`` belongs to that directory). The move writes the new file atomically and then
removes the old one, so an interrupted run leaves one or both files and running it again is safe.
"""

from __future__ import annotations

from pathlib import Path

from readcode import kbio


class MigrateError(RuntimeError):
    pass


def _studies(kb: Path, study: str | None) -> list[str]:
    if study is not None:
        if not (kbio.study_dir(kb, study) / "study.json").is_file():
            raise MigrateError(f"{kbio.study_dir(kb, study) / 'study.json'} not found; run `readcode init` first")
        return [study]
    if not kb.is_dir():
        raise MigrateError(f"{kb} is not a directory")
    return sorted(p.name for p in kb.iterdir() if (p / "study.json").is_file())


def _shas(sdir: Path) -> list[str]:
    snapshots = sdir / "snapshots"
    if not snapshots.is_dir():
        return []
    names = []
    for p in snapshots.iterdir():
        try:
            if p.is_dir() and kbio.safe_snapshot_dir(sdir, p.name):
                names.append(p.name)
        except kbio.UnsafeSnapshotError:
            continue
    return sorted(names)


def migrate_study(kb: Path | str, study: str | None = None) -> list[str]:
    """Migrate one study (all studies of ``kb`` when None); returns Spanish messages, one per change."""
    kb = Path(kb)
    moved: list[str] = []
    for name in _studies(kb, study):
        sdir = kbio.study_dir(kb, name)
        for sha in _shas(sdir):
            snap = kbio.snapshot_dir(sdir, sha)
            legacy = kbio.legacy_root_path(snap)
            if legacy is None:
                continue
            new = snap / kbio.ROOT_DIR_DOC
            where = f"{name}/snapshots/{sha}"
            if new.is_file():
                legacy.unlink()  # dir-root.json already wins; the old copy is dead weight
                moved.append(f"{where}: ya existía {kbio.ROOT_DIR_DOC}; se eliminó {kbio.LEGACY_ROOT_DIR_DOC}")
            else:
                kbio.atomic_write_bytes(new, legacy.read_bytes())
                legacy.unlink()
                moved.append(f"{where}: {kbio.LEGACY_ROOT_DIR_DOC} -> {kbio.ROOT_DIR_DOC}")
    return moved


def format_migrated(moved: list[str]) -> str:
    if not moved:
        return "Nada que migrar."
    return "\n".join(moved) + "\nEjecuta `readcode validate` para regenerar links.json y search.json."
