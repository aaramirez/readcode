"""``readcode archify``: render a diagram with the Archify CLI into a snapshot's diagrams/."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from readcode import kbio

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._-]+$", re.ASCII)  # same rule as [[archify:name]]


class ArchifyError(RuntimeError):
    """User-facing error; the CLI exits with code 2."""


def find_archify() -> Path:
    """$ARCHIFY_BIN, else ~/.agents/skills/archify, else ~/.claude/skills/archify."""
    env = os.environ.get("ARCHIFY_BIN")
    if env:
        p = Path(env)
        candidates = [p / "bin" / "archify.mjs", p / "archify.mjs"] if p.is_dir() else [p]
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
    """Resolve ``sha`` (full or unique prefix) against study.json; never leaves <study>/snapshots."""
    try:
        study_data = kbio.read_json(sdir / "study.json")
        shas = [s["sha"] for s in study_data["snapshots"]]
        full = kbio.resolve_sha({"snapshots": [{"sha": x} for x in shas if _SHA_RE.match(x)]}, sha)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchifyError(f"no existe el snapshot {sha} en {sdir}: {exc}") from exc
    snap = kbio.snapshot_dir(sdir, full)
    if not snap.is_dir():
        raise ArchifyError(f"no existe el snapshot {sha} en {sdir}")
    return snap


def render_diagram(kb: Path | str, study: str, sha: str, name: str, diagram_type: str,
                   input_json: Path | str, repo_root: Path | str | None = None,
                   quality: str | None = None) -> Path:
    """Run Archify ``finalize`` into diagrams/<name>.html (atomic), then copy the source to <name>.json."""
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
    # Stage and finalize in a temp dir: Archify requires a .html target and writes sidecars
    # (delivery.json, receipt, browser artifacts) next to it, none of which may reach the kb.
    work = Path(tempfile.mkdtemp(prefix="readcode-archify-"))
    staged = work / f"{name}.html"
    cmd = [node, str(archify), "finalize", diagram_type, str(src), str(staged), "--json",
           "--out-dir", str(work), "--receipt", str(work / "receipt.json")]
    if repo_root is not None:
        cmd += ["--repo-root", str(repo_root)]
    if quality is not None:
        cmd += ["--quality", quality]
    tmp: Path | None = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not staged.is_file() or staged.stat().st_size == 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ArchifyError(f"archify falló al finalizar {name} (código {proc.returncode}): {detail}")
        out_dir.mkdir(parents=True, exist_ok=True)
        # work dir may be on another drive: copy next to the target, then rename atomically
        fd, tmp_name = tempfile.mkstemp(dir=out_dir, prefix=f".{name}.", suffix=".tmp")
        os.close(fd)
        tmp = Path(tmp_name)
        shutil.copyfile(staged, tmp)
        os.replace(tmp, out_dir / f"{name}.html")
        tmp = None
        kbio.atomic_write_bytes(out_dir / f"{name}.json", src.read_bytes())
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)
    return out_dir / f"{name}.html"
