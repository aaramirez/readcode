"""``readcode graph``: run graphify over a snapshot materialized from blobs."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from readcode import kbio


class GraphError(RuntimeError):
    pass


def run_graphify(exe: str, directory: Path) -> None:
    """Run ``graphify update <directory>``; raises GraphError on failure (patched in tests)."""
    try:
        result = subprocess.run([exe, "update", str(directory)], capture_output=True, text=True)
    except OSError as exc:
        raise GraphError(f"could not run graphify: {exc}") from exc
    if result.returncode != 0:
        raise GraphError(f"graphify exited with {result.returncode}: {(result.stderr or result.stdout).strip()}")


def _set_tool(study_json: Path, study_data: dict, ok: bool) -> None:
    study_data.setdefault("tools", {})["graphify"] = ok
    kbio.atomic_write_json(study_json, study_data)


def graph_snapshot(kb: Path | str, study: str, sha: str) -> bool:
    """True on success. If graphify is missing or fails: warn on stderr, tools.graphify=false, False."""
    sdir = kbio.study_dir(kb, study)
    study_json = sdir / "study.json"
    if not study_json.is_file():
        raise GraphError(f"{study_json} not found; run `readcode init` first")
    study_data = kbio.read_json(study_json)
    try:
        sha = kbio.resolve_sha(study_data, sha, sdir)
    except ValueError as exc:
        raise GraphError(str(exc)) from exc
    snap = kbio.snapshot_dir(sdir, sha)
    tree_path = snap / "tree.json"
    if not tree_path.is_file():
        raise GraphError(f"{tree_path} not found; run `readcode snapshot` first")
    tree = kbio.read_json(tree_path)

    exe = shutil.which("graphify")
    if exe is None:
        print("warning: graphify no esta instalado; se omite el grafo", file=sys.stderr)
        _set_tool(study_json, study_data, False)
        return False

    with tempfile.TemporaryDirectory(prefix="readcode-graph-") as tmp:
        root = Path(tmp)
        for f in tree["files"]:
            kbio.atomic_write_bytes(root / f["path"], kbio.blob_path(sdir, f["blob"]).read_bytes())
        try:
            run_graphify(exe, root)
            graph = root / "graphify-out" / "graph.json"
            if not graph.is_file():
                raise GraphError("graphify did not produce graphify-out/graph.json")
            out = snap / "graph"
            kbio.atomic_write_bytes(out / "graph.json", graph.read_bytes())
            report = root / "graphify-out" / "GRAPH_REPORT.md"
            if report.is_file():
                kbio.atomic_write_bytes(out / "GRAPH_REPORT.md", report.read_bytes())
        except (GraphError, OSError) as exc:
            print(f"warning: graphify fallo: {exc}", file=sys.stderr)
            _set_tool(study_json, study_data, False)
            return False
    _set_tool(study_json, study_data, True)
    return True
