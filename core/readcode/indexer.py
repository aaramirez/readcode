"""``readcode index``: tree-sitter symbol extraction (defs, refs, imports) into symbols.json.

Queries per language = the grammar's bundled tags query (from tree-sitter-language-pack,
plus inherited ones, e.g. javascript for typescript) + readcode's own ``queries/<lang>.scm``.
Captures used: ``@name`` with ``@definition.<kind>`` / ``@reference.<kind>``, and
``@import.module`` (optionally ``@import.from`` for Python ``from X import a, b``).
"""

from __future__ import annotations

import posixpath
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from readcode import kbio
from readcode.schemas import validate

QUERIES_DIR = Path(__file__).resolve().parent / "queries"

# tree.json language -> tree-sitter-language-pack name (identity when absent)
PACK_NAMES = {"shell": "bash", "jsx": "javascript"}
# Languages with a grammar but no symbols worth indexing -> indexed: false.
NOT_INDEXED = {"markdown", "json", "yaml", "toml", "html", "css"}
# pack language -> bundled tags queries to combine (default: its own)
TAGS_FROM = {"typescript": ["javascript", "typescript"], "tsx": ["javascript", "tsx"]}
# pack language -> readcode query files to combine (default: its own, if present)
QUERY_FILES = {"typescript": ["javascript", "typescript"], "tsx": ["javascript", "tsx"]}

SCHEMA_KINDS = {
    "function", "method", "class", "interface", "type", "struct",
    "variable", "constant", "module", "table", "other",
}
KIND_ALIASES = {"constructor": "method", "enum": "type", "union": "type", "trait": "interface"}
CONTAINER_KINDS = {"class", "interface", "struct", "type", "module"}

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts")


class IndexingError(RuntimeError):
    """Raised for user-facing errors (missing study / snapshot)."""


@dataclass
class _Lang:
    language: object
    query: object | None  # None -> generic fallback (indexed, but no symbols)


# Pack names whose grammar could not be loaded (typically: download failed offline).
LOAD_FAILURES: set[str] = set()


@lru_cache(maxsize=None)
def _load(pack_name: str) -> _Lang | None:
    """Parser language + combined query for ``pack_name``; None if unsupported."""
    import tree_sitter_language_pack as tslp
    from tree_sitter import Query

    try:
        if not tslp.has_language(pack_name):
            return None
        language = tslp.get_language(pack_name)
    except Exception:  # unknown language, grammar download/load failure
        LOAD_FAILURES.add(pack_name)
        return None
    parts: list[str] = []
    for name in TAGS_FROM.get(pack_name, [pack_name]):
        parts.append(tslp.get_tags_query(name) or "")
    for name in QUERY_FILES.get(pack_name, [pack_name]):
        path = QUERIES_DIR / f"{name}.scm"
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    source = "\n".join(p for p in parts if p.strip())
    return _Lang(language, Query(language, source) if source else None)


def resolve_language(language: str | None) -> _Lang | None:
    if not language or language in NOT_INDEXED:
        return None
    return _load(PACK_NAMES.get(language, language))


# ---------------------------------------------------------------- extraction


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _col(source: bytes, node) -> int:
    """0-based column in characters (tree-sitter reports bytes)."""
    line_start = source.rfind(b"\n", 0, node.start_byte) + 1
    return len(source[line_start:node.start_byte].decode("utf-8", "replace"))


def _kind(tag: str) -> str:
    tag = KIND_ALIASES.get(tag, tag)
    return tag if tag in SCHEMA_KINDS else "other"


def _refine_kind(kind: str, node) -> str:
    if node.type == "type_spec":  # go: type X struct{...} / interface{...}
        inner = node.child_by_field_name("type")
        if inner is not None and inner.type == "struct_type":
            return "struct"
        if inner is not None and inner.type == "interface_type":
            return "interface"
    return kind


def _receiver_type(node, source: bytes) -> str | None:
    """Go methods: the receiver's type name (``func (q *Queue) Push()`` -> Queue)."""
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return None
    stack = [receiver]
    while stack:
        current = stack.pop(0)
        if current.type == "type_identifier":
            return _text(current, source)
        stack.extend(current.children)
    return None


def _contains(outer, inner) -> bool:
    return (
        outer.start_byte <= inner.start_byte
        and inner.end_byte <= outer.end_byte
        and (outer.start_byte, outer.end_byte) != (inner.start_byte, inner.end_byte)
    )


def extract(source: bytes, language: str, path: str, paths: frozenset[str],
            go_modules: dict[str, str | None] | None = None) -> dict | None:
    """Symbols of one file ``{defs, refs, imports}``; None if the language is unsupported.

    ``go_modules`` maps a directory ("" = repo root) to the module path of its go.mod.
    """
    from tree_sitter import Parser, QueryCursor

    lang = resolve_language(language)
    if lang is None:
        return None
    tree = Parser(lang.language).parse(source)
    if lang.query is None:
        return {"defs": [], "refs": [], "imports": []}

    raw_defs: list[tuple[str, object, object]] = []  # (kind, def node, name node)
    raw_refs: list[object] = []  # name nodes
    raw_imports: list[tuple[object, object | None]] = []  # (module node, from-statement)
    for _, caps in QueryCursor(lang.query).matches(tree.root_node):
        names = caps.get("name") or []
        if "import.module" in caps:
            stmt = (caps.get("import.from") or [None])[0]
            raw_imports.extend((n, stmt) for n in caps["import.module"])
            continue
        for capture, nodes in caps.items():
            if capture.startswith("definition.") and names:
                raw_defs.append((capture.split(".", 1)[1], nodes[0], names[0]))
            elif capture.startswith("reference.") and names:
                raw_refs.extend(names)

    # Go blank identifiers (`var _ I = (*T)(nil)`) declare nothing.
    defs = _build_defs([r for r in raw_defs if not (language == "go" and _text(r[2], source) == "_")],
                       source)
    def_names = {(n.start_byte, n.end_byte) for _, _, n in raw_defs}
    refs: dict[tuple, dict] = {}
    for node in raw_refs:
        if (node.start_byte, node.end_byte) in def_names:
            continue
        if node.parent is not None and node.parent.type == "type_parameter":
            continue  # generic parameter declaration, not a use
        line = node.start_point[0] + 1
        ref = {"name": _text(node, source), "line": line, "col": _col(source, node)}
        refs[(ref["line"], ref["col"], ref["name"])] = ref
    imports = _build_imports(raw_imports, source, language, path, paths, go_modules or {})
    return {"defs": defs, "refs": [refs[k] for k in sorted(refs)], "imports": imports}


def _build_defs(raw_defs, source: bytes) -> list[dict]:
    seen: dict[tuple, dict] = {}
    items: list[tuple[dict, object]] = []
    for tag, node, name_node in raw_defs:
        kind = _refine_kind(_kind(tag), node)
        name = _text(name_node, source)
        rng = [node.start_point[0] + 1, node.end_point[0] + 1]
        key = (name, rng[0], rng[1], name_node.start_byte)
        if key in seen:  # same symbol from two queries: keep the more specific kind
            if seen[key]["kind"] == "other" and kind != "other":
                seen[key]["kind"] = kind
            continue
        d = {"name": name, "kind": kind, "range": rng}
        seen[key] = d
        items.append((d, node))

    for d, node in items:
        parent = _receiver_type(node, source)
        if parent is None:
            enclosing = [(od, on) for od, on in items if _contains(on, node)]
            if enclosing:  # only a direct container counts (not a nested function's)
                inner = min(enclosing, key=lambda c: c[1].end_byte - c[1].start_byte)[0]
                if inner["kind"] in CONTAINER_KINDS:
                    parent = inner["name"]
        if parent is not None:
            d["parent"] = parent
            if d["kind"] == "function":
                d["kind"] = "method"
    defs = [d for d, _ in items]
    defs.sort(key=lambda d: (d["range"][0], d["range"][1], d["name"]))
    return defs


# ------------------------------------------------------------------- imports


def _build_imports(raw, source: bytes, language: str, path: str, paths: frozenset[str],
                   go_modules: dict[str, str | None]) -> list[dict]:
    out: list[dict] = []
    for node, stmt in sorted(raw, key=lambda r: r[0].start_byte):
        module = _text(node, source)
        line = node.start_point[0] + 1
        if language == "python":
            out.extend(_python_imports(module, line, stmt, source, path, paths))
        elif language in ("typescript", "tsx", "javascript", "jsx"):
            out.append({"module": module, "line": line, "resolved": _resolve_js(module, path, paths)})
        elif language == "java":
            out.append({"module": module, "line": line, "resolved": _resolve_java(module, paths)})
        else:  # go: packages are directories -> `resolvedDir` (`resolved` stays null)
            imp = {"module": module, "line": line, "resolved": None}
            resolved_dir = _resolve_go_dir(module, path, paths, go_modules)
            if resolved_dir is not None:
                imp["resolvedDir"] = resolved_dir
            out.append(imp)
    unique: dict[tuple, dict] = {}
    for imp in out:
        unique.setdefault((imp["line"], imp["module"]), imp)
    return list(unique.values())


def _python_module_file(dotted: str, path: str, paths: frozenset[str]) -> str | None:
    """Resolve ``a.b`` / ``.a`` / ``..`` to ``a/b.py`` or ``a/b/__init__.py``."""
    level = len(dotted) - len(dotted.lstrip("."))
    rest = dotted[level:]
    if level:
        base = PurePosixPath(path).parent
        for _ in range(level - 1):
            base = base.parent
        bases = [str(base) if str(base) != "." else ""]
    else:
        bases = ["", "src"]
    for base in bases:
        stem = posixpath.join(base, *rest.split(".")) if rest else base
        candidates = [f"{stem}.py", posixpath.join(stem, "__init__.py")] if stem else ["__init__.py"]
        for candidate in candidates:
            if candidate in paths:
                return candidate
    return None


def _python_imports(module, line, stmt, source, path, paths) -> list[dict]:
    resolved = _python_module_file(module, path, paths)
    if stmt is None or (resolved and not resolved.endswith("__init__.py")):
        return [{"module": module, "line": line, "resolved": resolved}]
    # `from pkg import a, b`: when a/b are submodules, record each one.
    out = []
    for name_node in stmt.children_by_field_name("name"):
        if name_node.type == "aliased_import":
            name_node = name_node.child_by_field_name("name")
        sub = f"{module}{'' if module.endswith('.') else '.'}{_text(name_node, source)}"
        sub_resolved = _python_module_file(sub, path, paths)
        if sub_resolved:
            out.append({"module": sub, "line": line, "resolved": sub_resolved})
    return out or [{"module": module, "line": line, "resolved": resolved}]


def _resolve_js(module: str, path: str, paths: frozenset[str]) -> str | None:
    if not module.startswith("."):
        return None  # bare specifier (package)
    target = posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
    candidates = [target]
    stem, ext = posixpath.splitext(target)
    if ext in (".js", ".jsx", ".mjs", ".cjs"):  # TS-style "./x.js" pointing at x.ts
        candidates += [stem + e for e in (".ts", ".tsx")]
    candidates += [target + e for e in JS_EXTENSIONS]
    candidates += [posixpath.join(target, "index" + e) for e in JS_EXTENSIONS]
    return next((c for c in candidates if c in paths), None)


def _strip_go_comment(line: str) -> str:
    """Drop a trailing ``//`` comment, ignoring ``//`` inside quotes."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in ('"', "`"):
            quote = ch
        elif line.startswith("//", i):
            return line[:i]
    return line


def _unquote_go(value: str) -> str:
    value = value.strip()
    if len(value) > 1 and value[0] in ('"', "`") and value[-1] == value[0]:
        return value[1:-1]
    return value


def _parse_go_module(text: str) -> str | None:
    """The path of the ``module`` directive of a go.mod (line or block form), or None."""
    lines = [_strip_go_comment(raw).strip() for raw in text.lstrip("﻿").splitlines()]
    for i, line in enumerate(lines):
        if not line.startswith("module") or line[6:7] not in (" ", "	", "("):
            continue
        rest = line[6:].strip()
        if rest.startswith("("):
            rest = rest[1:].strip().rstrip(")").strip()
            if not rest:  # block form: path on the following line
                rest = next((ln.rstrip(")").strip() for ln in lines[i + 1:] if ln.strip(") ")), "")
        return _unquote_go(rest) or None
    return None


@lru_cache(maxsize=4)
def _go_dirs(paths: frozenset[str]) -> frozenset[str]:
    """Directories ("" = root) that directly contain at least one .go file."""
    return frozenset(posixpath.dirname(p) for p in paths if p.endswith(".go"))


def _resolve_go_dir(module: str, path: str, paths: frozenset[str],
                    go_modules: dict[str, str | None]) -> str | None:
    """Directory of a package imported from the nearest go.mod's module, if it has .go files.

    ``""`` is the repo root (the module root package); callers must test ``is not None``.
    """
    directory = posixpath.dirname(path)
    while directory not in go_modules:
        if not directory:
            return None
        directory = posixpath.dirname(directory)
    prefix = go_modules[directory]
    if prefix is None:  # unreadable go.mod: still a module boundary, imports unresolved
        return None
    if module == prefix:
        sub = ""
    elif module.startswith(prefix + "/"):
        sub = module[len(prefix) + 1:].strip("/")
    else:
        return None
    target = posixpath.join(directory, sub) if directory else sub
    for other in go_modules:  # target inside a nested module -> not part of this one
        if (other != directory
                and (other == target or target.startswith(other + "/"))
                and (other.startswith(directory + "/") or not directory)):
            return None
    return target if target in _go_dirs(paths) else None


def _resolve_java(module: str, paths: frozenset[str]) -> str | None:
    parts = module.split(".")
    for end in (len(parts), len(parts) - 1):  # class import, or static member import
        if end < 1:
            continue
        suffix = "/".join(parts[:end]) + ".java"
        matches = sorted(p for p in paths if p == suffix or p.endswith("/" + suffix))
        if len(matches) == 1:
            return matches[0]
    return None


# ------------------------------------------------------------------ command


def _find_snapshot(sdir: Path, sha: str) -> Path:
    def safe(name: str) -> Path | None:
        try:
            return kbio.safe_snapshot_dir(sdir, name)
        except kbio.UnsafeSnapshotError:
            return None

    exact = safe(sha)
    if exact is not None and (exact / "tree.json").is_file():
        return exact
    root = sdir / "snapshots"
    matches = [safe(p.name) for p in root.iterdir() if p.name.startswith(sha)] if root.is_dir() and sha else []
    matches = [p for p in matches if p is not None and (p / "tree.json").is_file()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise IndexingError(f"No snapshot {sha} in {sdir}; run `readcode snapshot` first")
    raise IndexingError(f"Ambiguous sha prefix {sha!r}: {', '.join(p.name for p in matches)}")


def _read_go_modules(sdir: Path, tree: dict) -> dict[str, str | None]:
    """``{directory: module path}`` for every go.mod in the snapshot (warns once if unreadable).

    An unreadable go.mod maps to None: it still bounds the module above it."""
    modules: dict[str, str | None] = {}
    bad: list[str] = []
    for entry in tree["files"]:
        if posixpath.basename(entry["path"]) != "go.mod":
            continue
        try:
            text = kbio.blob_path(sdir, entry["blob"]).read_bytes().decode("utf-8-sig")
            module = _parse_go_module(text)
        except (OSError, UnicodeDecodeError):
            module = None
        if module is None:
            bad.append(entry["path"])
        modules[posixpath.dirname(entry["path"])] = module
    if bad:
        print(f"aviso: no se pudo leer la línea `module` de {', '.join(bad)}; "
              "los imports de Go de ese módulo quedan sin resolver", file=sys.stderr)
    return modules


def index_snapshot(kb: Path | str, study: str, sha: str) -> dict:
    """Index a snapshot; rewrites tree.json ``indexed`` flags and writes symbols.json.

    Returns ``{"sha", "indexed", "skipped", "failed"}`` (``failed`` files raised while being
    extracted; each one is reported on stderr and counts as skipped).
    """
    sdir = kbio.study_dir(kb, study)
    if not (sdir / "study.json").is_file():
        raise IndexingError(f"{sdir / 'study.json'} not found; run `readcode init` first")
    snap = _find_snapshot(sdir, sha)
    LOAD_FAILURES.clear()  # per run; _load is cached, so drop it to re-record failures
    _load.cache_clear()
    tree = kbio.read_json(snap / "tree.json")
    paths = frozenset(f["path"] for f in tree["files"])

    go_modules = _read_go_modules(sdir, tree)

    files: dict[str, dict] = {}
    failed = 0
    for entry in tree["files"]:
        result = None
        try:
            source = kbio.blob_path(sdir, entry["blob"]).read_bytes()
            result = extract(source, entry["language"], entry["path"], paths, go_modules)
        except Exception as exc:  # one bad file never aborts the run
            print(f"aviso: no se pudo indexar {entry['path']} ({type(exc).__name__})", file=sys.stderr)
            failed += 1
            result = None
        entry["indexed"] = result is not None
        if result is not None:
            files[entry["path"]] = result

    if LOAD_FAILURES:
        print(f"aviso: no se pudo cargar la gramática de {', '.join(sorted(LOAD_FAILURES))}; "
              "si falta red, ejecuta `readcode grammars --fetch` y vuelve a indexar", file=sys.stderr)
    symbols = {"schemaVersion": 1, "sha": tree["sha"], "files": files}
    for kind, data in (("symbols", symbols), ("tree", tree)):
        errors = validate(kind, data)
        if errors:
            raise IndexingError(f"Invalid {kind}.json: " + "; ".join(errors[:10]))
    kbio.atomic_write_json(snap / "symbols.json", symbols)
    kbio.atomic_write_json(snap / "tree.json", tree)
    _upgrade_status(sdir, tree["sha"], snap)
    return {"sha": tree["sha"], "indexed": len(files), "skipped": len(tree["files"]) - len(files),
            "failed": failed}


def _upgrade_status(sdir: Path, sha: str, snap: Path) -> None:
    """A "partial" snapshot with no explain/ files yet becomes "indexed" in study.json."""
    study_json = sdir / "study.json"
    study_data = kbio.read_json(study_json)
    entry = next((s for s in study_data.get("snapshots", []) if s.get("sha") == sha), None)
    explain = snap / "explain"
    if entry is None or entry.get("status") != "partial":
        return
    if explain.is_dir() and any(p.is_file() for p in explain.rglob("*.json")):
        return
    entry["status"] = "indexed"
    errors = validate("study", study_data)
    if errors:
        raise IndexingError("Invalid study.json: " + "; ".join(errors[:10]))
    kbio.atomic_write_json(study_json, study_data)
