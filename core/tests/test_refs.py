from readcode.refs import parse_markers, resolve, resolve_all


def one(md):
    ms = parse_markers(md)
    assert len(ms) == 1
    return ms[0]


def test_symbol_with_path():
    m = one("a [[ref:app/x.py#f]] b")
    assert (m.kind, m.path, m.symbol, m.label) == ("symbol", "app/x.py", "f", None)
    assert m.raw == "[[ref:app/x.py#f]]" and m.span == (2, 20)


def test_symbol_current_file_and_dotted():
    m = one("[[ref:#Cls.meth]]")
    assert (m.kind, m.path, m.symbol) == ("symbol", None, "Cls.meth")


def test_lines_range_and_single():
    m = one("[[ref:a/b.py:L10-31]]")
    assert (m.kind, m.path, m.range) == ("lines", "a/b.py", (10, 31))
    m = one("[[ref:a/b.py:L7]]")
    assert m.range == (7, 7)


def test_label():
    m = one("[[ref:a.py#f|texto visible]]")
    assert (m.symbol, m.label) == ("f", "texto visible")
    m = one("[[ref:a.py:L1-2|ver]]")
    assert (m.range, m.label) == ((1, 2), "ver")


def test_archify():
    m = one("[[archify:overview]]")
    assert (m.kind, m.symbol) == ("archify", "overview")


def test_ignored_in_fence_and_inline():
    md = ("```\n[[ref:a.py#f]]\n```\n`[[ref:b.py#g]]`\n~~~~\n[[ref:c#d]]\n~~~\n"
          "[[ref:z#z]]\n~~~~\n[[ref:ok#ok]]")
    ms = parse_markers(md)
    assert [m.symbol for m in ms] == ["ok"]
    assert md[ms[0].span[0]:ms[0].span[1]] == "[[ref:ok#ok]]"


def test_invalid():
    for raw in ["[[ref:]]", "[[ref:path]]", "[[archify:]]", "[[ref:a.py#]]",
                "[[ref:a.py#f|]]"]:
        m = one(raw)
        assert m.kind == "invalid" and m.raw == raw


def L(path, lines):
    return {"path": path, "lines": lines}


TREE = {"files": [L("app/main.py", 50), L("app/util.py", 30), L("lib/other.py", 20)]}
SYMS = {"files": {
    "app/main.py": {"defs": [
        {"name": "main", "kind": "function", "range": [1, 10]},
        {"name": "Svc", "kind": "class", "range": [12, 40]},
        {"name": "run", "kind": "method", "range": [14, 20], "parent": "Svc"},
        {"name": "dup", "kind": "function", "range": [41, 42]},
        {"name": "dup", "kind": "function", "range": [45, 46]},
    ], "refs": [], "imports": [{"module": "util", "line": 1, "resolved": "app/util.py"},
                               {"module": "os", "line": 2, "resolved": None}]},
    "app/util.py": {"defs": [
        {"name": "helper", "kind": "function", "range": [3, 9]},
        {"name": "process", "kind": "function", "range": [10, 15]},
        {"name": "run", "kind": "method", "range": [20, 25], "parent": "Other"},
    ], "refs": [], "imports": []},
    "lib/other.py": {"defs": [
        {"name": "process", "kind": "function", "range": [1, 5]},
        {"name": "deep", "kind": "function", "range": [6, 8]},
    ], "refs": [], "imports": []},
}}


def res(marker_text, cur="app/main.py", **kw):
    return resolve(one(marker_text), cur, TREE, SYMS, **kw)


def test_explicit_path_exact_and_first_of_dups():
    r = res("[[ref:app/main.py#dup]]")
    assert (r.status, r.target, r.range) == ("exact", "app/main.py", (41, 42))


def test_explicit_path_broken():
    assert res("[[ref:app/main.py#nope]]").status == "broken"
    assert res("[[ref:missing.py#main]]").status == "broken"


def test_tier_current_file():
    r = res("[[ref:#main]]")
    assert (r.status, r.target, r.range) == ("exact", "app/main.py", (1, 10))


def test_tier_imports_before_repo():
    r = res("[[ref:#helper]]")
    assert (r.status, r.target) == ("exact", "app/util.py")


def test_tier_repo():
    r = res("[[ref:#deep]]")
    assert (r.status, r.target) == ("exact", "lib/other.py")


def test_process_resolved_by_earlier_tier():
    # imports tier (app/util.py) has exactly one match, so it wins over repo
    r = res("[[ref:#process]]", cur="app/main.py")
    assert (r.status, r.target) == ("exact", "app/util.py")
    r = res("[[ref:#process]]", cur="lib/other.py")
    assert (r.status, r.target) == ("exact", "lib/other.py")


def test_ambiguous_all_candidates():
    empty = {"defs": [], "refs": [], "imports": []}
    syms = {"files": {**SYMS["files"], "app/main.py": empty}}
    r = resolve(one("[[ref:#process]]"), "app/main.py", TREE, syms)
    assert r.status == "ambiguous" and r.target is None
    assert r.candidates == [("app/util.py", (10, 15)), ("lib/other.py", (1, 5))]
    assert r.to_link_entry() == {
        "raw": "[[ref:#process]]", "kind": "symbol", "status": "ambiguous",
        "candidates": [{"target": "app/util.py", "range": [10, 15]},
                       {"target": "lib/other.py", "range": [1, 5]}]}


def test_ambiguous_within_current_file():
    assert res("[[ref:#dup]]").status == "ambiguous"


def test_ambiguous_repo_tier():
    syms = {"files": {
        "a.py": {"defs": [], "refs": [], "imports": []},
        "b.py": {"defs": [{"name": "process", "kind": "function", "range": [1, 2]}],
                 "refs": [], "imports": []},
        "c.py": {"defs": [{"name": "process", "kind": "function", "range": [3, 4]}],
                 "refs": [], "imports": []},
    }}
    r = resolve(one("[[ref:#process]]"), "a.py", TREE, syms)
    assert r.status == "ambiguous" and len(r.candidates) == 2


def test_class_method():
    r = res("[[ref:#Svc.run]]")
    assert (r.status, r.target, r.range) == ("exact", "app/main.py", (14, 20))
    r = res("[[ref:app/util.py#Other.run]]")
    assert (r.target, r.range) == ("app/util.py", (20, 25))
    assert res("[[ref:#Nope.run]]").status == "broken"


def test_broken_symbol_anywhere():
    assert res("[[ref:#ghost]]").status == "broken"


def test_lines():
    r = res("[[ref:app/util.py:L1-30]]")
    assert (r.status, r.target, r.range) == ("exact", "app/util.py", (1, 30))
    assert res("[[ref:app/util.py:L1-31]]").status == "broken"
    assert res("[[ref:app/util.py:L0-3]]").status == "broken"
    assert res("[[ref:app/util.py:L9-3]]").status == "broken"
    assert res("[[ref:nope.py:L1-2]]").status == "broken"
    assert res("[[ref::L5]]").target == "app/main.py"


def test_archify_and_invalid():
    r = res("[[archify:flow]]")
    assert r.to_link_entry() == {"raw": "[[archify:flow]]", "kind": "archify",
                                 "status": "exact", "target": "diagrams/flow.html"}
    assert res("[[archify:flow]]", diagrams={"other.html"}).status == "broken"
    assert res("[[archify:flow]]", diagrams={"flow.html"}).status == "exact"
    r = res("[[ref:]]")
    assert r.to_link_entry() == {"raw": "[[ref:]]", "kind": "invalid", "status": "broken"}


def test_exact_link_entry():
    assert res("[[ref:app/main.py#main]]").to_link_entry() == {
        "raw": "[[ref:app/main.py#main]]", "kind": "symbol", "status": "exact",
        "target": "app/main.py", "range": [1, 10]}


def test_resolve_all():
    out = resolve_all("x [[ref:#main]] y [[ref:#ghost]]", "app/main.py", TREE, SYMS)
    assert [r.status for _, r in out] == ["exact", "broken"]


def test_stray_backtick_does_not_swallow_across_paragraphs():
    md = "use `tick here\n\nsee [[ref:a.py#f]]\n\nstray ` end"
    assert [m.symbol for m in parse_markers(md)] == ["f"]


def test_multi_backtick_inline_span():
    md = "``a `b` [[ref:x.py#in]] c`` then [[ref:y.py#out]]"
    assert [m.symbol for m in parse_markers(md)] == ["out"]


def test_two_markers_one_line():
    ms = parse_markers("[[ref:a.py#f]] y [[ref:b.py:L1-2]]")
    assert [m.kind for m in ms] == ["symbol", "lines"]


def test_unicode_digits_not_lines():
    assert one("[[ref:a.py:L\u0661]]").kind == "invalid"


def test_repo_tier_candidates_sorted():
    d = {"defs": [{"name": "p", "kind": "function", "range": [9, 9]},
                  {"name": "p", "kind": "function", "range": [2, 2]}],
         "refs": [], "imports": []}
    syms = {"files": {"z.py": d, "b.py": d, "cur.py": {"defs": [], "refs": [], "imports": []}}}
    r = resolve(one("[[ref:#p]]"), "cur.py", TREE, syms)
    assert [c for c in r.candidates] == [("b.py", (2, 2)), ("b.py", (9, 9)),
                                         ("z.py", (2, 2)), ("z.py", (9, 9))]
