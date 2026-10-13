"""Marker parsing and reference resolution for readcode studies.

Pure library: no I/O, no CLI.

Marker grammar (the TypeScript viewer must re-implement exactly this)
---------------------------------------------------------------------
Markers are searched in the Markdown source, OUTSIDE fenced code blocks
(``` or ~~~, closed by a fence of the same character and at least the same
length) and OUTSIDE inline code spans. Inline code is resolved per paragraph
(paragraphs are separated by a blank line: a newline, optional spaces/tabs,
a newline; fenced lines count as blank for this purpose): scanning left to
right, a run of N backticks opens a span closed by the next run of exactly N
backticks in the SAME paragraph; an opener with no closer in its paragraph is
literal text and the span never crosses a blank line.

Whitespace means exactly: space, tab, LF, CR, form feed, vertical tab.
Digits are [0-9] only. Character classes are ASCII-only; offsets in
Marker.span are Python code-point offsets into the source (the viewer must
not rely on them).

    marker   = "[[" body "]]"
    body     = "ref:" refbody | "archify:" name
    refbody  = target [ "|" label ]
    target   = path "#" symbol          -> kind "symbol"
             | "#" symbol               -> kind "symbol", path = None (current file)
             | path ":L" N "-" M        -> kind "lines"
             | path ":L" N              -> kind "lines" (range N-N)
    path     = chars except whitespace, "#", ":", "|", "[", "]"  (empty only
               for the "#symbol" form and the lines form; empty = current file)
    symbol   = one or more chars except whitespace, "|", "[", "]", "#"
               ("Class.method" is allowed; the last "." splits parent/name)
    N, M     = decimal digits
    label    = any chars except "]" and newline (non-empty)
    name     = one or more of [A-Za-z0-9._-], not containing ".." (no label,
               no path separators: it names diagrams/<name>.html)

The body never contains "]" or a newline. Anything that starts with
"[[ref:" or "[[archify:" and closes with "]]" but does not match the grammar
(e.g. "[[ref:]]", "[[ref:path]]", "[[archify:]]") is returned with kind
"invalid" and its raw text, so `validate` can report it.

Marker.symbol holds the diagram name for archify markers.

Resolution
----------
See `resolve`. Tier-3 (whole repo) candidates are sorted by path, then by
start line, so ambiguous results are deterministic.

Archify markers resolve to target "diagrams/<name>.html";
existence is checked by the caller: pass `diagrams` (a set of names, with or
without extension) to get "broken" for unknown diagrams; when `diagrams` is
None the status is "exact" (validate checks existence later).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

Range = tuple[int, int]

_WS = r" \t\n\r\f\v"  # regex-escaped class body: ASCII whitespace only
_MARKER_RE = re.compile(r"\[\[(ref|archify):([^\]\n]*)\]\]", re.ASCII)
_LINES_RE = re.compile(rf"^([^{_WS}#:|\[\]]*):L([0-9]+)(?:-([0-9]+))?$", re.ASCII)
_SYMBOL_RE = re.compile(rf"^([^{_WS}#:|\[\]]*)#([^{_WS}|\[\]#]+)$", re.ASCII)
_ARCHIFY_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._-]+$", re.ASCII)
_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_BACKTICKS_RE = re.compile(r"`+")
_PARA_SEP_RE = re.compile(r"\n[ \t]*\n")


@dataclass(frozen=True)
class Marker:
    kind: str  # symbol | lines | archify | invalid
    raw: str
    span: tuple[int, int]  # [start, end) char offsets in the source
    path: str | None = None
    symbol: str | None = None  # for archify: the diagram name
    range: Range | None = None
    label: str | None = None


@dataclass
class Resolution:
    raw: str
    kind: str
    status: str  # exact | ambiguous | broken
    target: str | None = None
    range: Range | None = None
    candidates: list[tuple[str, Range]] = field(default_factory=list)

    def to_link_entry(self) -> dict:
        """Dict for a links.json marker entry (links.schema.json)."""
        entry: dict = {"raw": self.raw, "kind": self.kind, "status": self.status}
        if self.target is not None:
            entry["target"] = self.target
        if self.range is not None:
            entry["range"] = list(self.range)
        if self.candidates:
            entry["candidates"] = [
                {"target": t, "range": list(r)} for t, r in self.candidates
            ]
        return entry


# ---------------------------------------------------------------- parsing


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _mask_code(text: str) -> str:
    """Replace fenced blocks and inline code by spaces (same length)."""
    out: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(2)[0], len(m.group(2)))
                out.append(_blank(line))
            else:
                out.append(line)
        else:
            out.append(_blank(line))
            if (m and m.group(2)[0] == fence[0] and len(m.group(2)) >= fence[1]
                    and line[m.end():].strip() == ""):
                fence = None
    masked = "".join(out)
    parts, pos = [], 0
    for sep in _PARA_SEP_RE.finditer(masked):
        parts.append(_mask_inline(masked[pos:sep.start()]))
        parts.append(sep.group(0))
        pos = sep.end()
    parts.append(_mask_inline(masked[pos:]))
    return "".join(parts)


def _mask_inline(para: str) -> str:
    """Blank inline code spans within one paragraph (linear scan)."""
    runs = [(m.start(), m.end()) for m in _BACKTICKS_RE.finditer(para)]
    out, last, i = [], 0, 0
    while i < len(runs):
        n = runs[i][1] - runs[i][0]
        j = next((k for k in range(i + 1, len(runs))
                  if runs[k][1] - runs[k][0] == n), None)
        if j is None:
            i += 1
            continue
        out.append(para[last:runs[i][0]])
        out.append(_blank(para[runs[i][0]:runs[j][1]]))
        last = runs[j][1]
        i = j + 1
    out.append(para[last:])
    return "".join(out)


def _parse_one(kind_word: str, body: str, raw: str, span: tuple[int, int]) -> Marker:
    invalid = Marker("invalid", raw, span)
    if kind_word == "archify":
        if _ARCHIFY_RE.match(body):
            return Marker("archify", raw, span, symbol=body)
        return invalid
    target, sep, label = body.partition("|")
    if sep and not label:
        return invalid
    label_v = label if sep else None
    m = _LINES_RE.match(target)
    if m:
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) is not None else start
        return Marker("lines", raw, span, path=m.group(1) or None,
                      range=(start, end), label=label_v)
    m = _SYMBOL_RE.match(target)
    if m:
        return Marker("symbol", raw, span, path=m.group(1) or None,
                      symbol=m.group(2), label=label_v)
    return invalid


def parse_markers(markdown: str) -> list[Marker]:
    masked = _mask_code(markdown)
    markers = []
    for m in _MARKER_RE.finditer(masked):
        span = (m.start(), m.end())
        markers.append(_parse_one(m.group(1), m.group(2), markdown[span[0]:span[1]], span))
    return markers


# -------------------------------------------------------------- resolving


def _matches(defs: list[dict], symbol: str) -> list[dict]:
    parent, dot, tail = symbol.rpartition(".")
    out = []
    for d in defs:
        if d["name"] == symbol:
            out.append(d)
        elif dot and d["name"] == tail and d.get("parent") == parent.rpartition(".")[2]:
            out.append(d)
    return out


def _candidates(files: dict, paths: list[str], symbol: str) -> list[tuple[str, Range]]:
    result = []
    for p in paths:
        for d in _matches(files.get(p, {}).get("defs", []), symbol):
            result.append((p, (d["range"][0], d["range"][1])))
    return result


def resolve(marker: Marker, current_path: str, tree: dict, symbols: dict,
            diagrams: set[str] | None = None) -> Resolution:
    """Resolve one marker against tree.json / symbols.json contents (dicts).

    lines: exact iff the file is in the tree and 1 <= start <= end <= lines.
    symbol with path: exact (first definition) iff that file defines it.
    symbol without path: tiers current file -> imported files -> whole repo;
    the first tier with matches decides (1 -> exact, >1 -> ambiguous with all
    candidates of that tier); none -> broken. "Class.method" matches a def
    named method whose parent is Class.
    archify: target "diagrams/<name>.html"; exact unless `diagrams` is given
    and lacks the name (names compared without ".html"/".mmd").
    invalid: broken.
    """
    base = Resolution(marker.raw, marker.kind, "broken")
    if marker.kind == "invalid":
        return base
    if marker.kind == "archify":
        name = marker.symbol or ""
        base.target = f"diagrams/{name}.html"
        known = None if diagrams is None else {
            re.sub(r"\.(html|mmd)$", "", d) for d in diagrams}
        base.status = "exact" if known is None or name in known else "broken"
        return base

    path = marker.path or current_path
    if marker.kind == "lines":
        info = next((f for f in tree.get("files", []) if f["path"] == path), None)
        s, e = marker.range  # type: ignore[misc]
        if info is not None and 1 <= s <= e <= info["lines"]:
            base.status, base.target, base.range = "exact", path, marker.range
        return base

    files = symbols.get("files", {})
    symbol = marker.symbol or ""
    if marker.path:
        found = _candidates(files, [marker.path], symbol)
        if found:
            base.status = "exact"
            base.target, base.range = found[0]
        return base

    imported = [i["resolved"] for i in files.get(current_path, {}).get("imports", [])
                if i.get("resolved")]
    tiers = [[current_path], list(dict.fromkeys(imported)), sorted(files)]
    for t, paths in enumerate(tiers):
        found = _candidates(files, paths, symbol)
        if t == 2:
            found.sort(key=lambda c: (c[0], c[1]))
        if len(found) == 1:
            base.status = "exact"
            base.target, base.range = found[0]
            return base
        if found:
            base.status, base.candidates = "ambiguous", found
            return base
    return base


def resolve_all(markdown: str, current_path: str, tree: dict, symbols: dict,
                diagrams: set[str] | None = None) -> list[tuple[Marker, Resolution]]:
    return [(m, resolve(m, current_path, tree, symbols, diagrams))
            for m in parse_markers(markdown)]
