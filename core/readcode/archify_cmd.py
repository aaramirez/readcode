"""``readcode archify``: render a diagram with the Archify CLI into a snapshot's diagrams/."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from readcode import kbio

NAME_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._-]+$", re.ASCII)  # same rule as [[archify:name]]


class ArchifyError(RuntimeError):
    """User-facing error; the CLI exits with code 2."""


def find_archify() -> Path:
    """$ARCHIFY_BIN, else ~/.agents/skills/archify, else ~/.claude/skills/archify."""
    env = os.environ.get("ARCHIFY_BIN")
    if env:
        candidates = [Path(env)]
    else:
        home = Path.home()
        candidates = [home / ".agents/skills/archify/bin/archify.mjs",
                      home / ".claude/skills/archify/bin/archify.mjs"]
    for c in candidates:
        if c.is_file():
            return c
    raise ArchifyError("no se encontró archify.mjs (define ARCHIFY_BIN o instala Archify: "
                       "`npx skills add tt-a1i/archify -g`)")


def _find_snapshot_dir(sdir: Path, sha: str) -> Path:
    exact = kbio.snapshot_dir(sdir, sha)
    if exact.is_dir():
        return exact
    root = sdir / "snapshots"
    matches = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(sha)] \
        if root.is_dir() and sha else []
    if len(matches) != 1:
        raise ArchifyError(f"no existe el snapshot {sha} en {sdir}" if not matches
                           else f"prefijo de sha ambiguo: {sha}")
    return matches[0]


def render_diagram(kb: Path | str, study: str, sha: str, name: str, diagram_type: str,
                   input_json: Path | str) -> Path:
    """Copy the source to diagrams/<name>.json and render diagrams/<name>.html atomically."""
    if not NAME_RE.match(name):
        raise ArchifyError(f"nombre de diagrama inválido: {name!r} (usa [A-Za-z0-9._-], sin '..')")
    src = Path(input_json)
    if not src.is_file():
        raise ArchifyError(f"no existe el archivo de entrada {src}")
    sdir = kbio.study_dir(kb, study)
    if not (sdir / "study.json").is_file():
        raise ArchifyError(f"no existe el estudio {study} en {kb}")
    snap = _find_snapshot_dir(sdir, sha)
    node = shutil.which("node")
    if not node:
        raise ArchifyError("no se encontró `node` en el PATH (Archify lo necesita)")
    archify = find_archify()

    out_dir = snap / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=out_dir, prefix=f".{name}.", suffix=".html.tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        proc = subprocess.run([node, str(archify), "render", diagram_type, str(src), str(tmp)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or tmp.stat().st_size == 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ArchifyError(f"archify falló al renderizar {name} (código {proc.returncode}): {detail}")
        kbio.atomic_write_bytes(out_dir / f"{name}.json", src.read_bytes())
        os.replace(tmp, out_dir / f"{name}.html")
    finally:
        tmp.unlink(missing_ok=True)
    return out_dir / f"{name}.html"
