# Task 5 report
Implemented core/readcode/refs.py (parse_markers, resolve, resolve_all, Marker, Resolution.to_link_entry) and core/tests/test_refs.py.
Tests: `python -m pytest core/tests/test_refs.py -q` -> 22 passed. Tests written alongside implementation (no separate RED run recorded).
Decisions: archify resolve() takes optional `diagrams` set; None -> exact (validate checks later), set lacking name -> broken. Lines marker with empty path (`[[ref::L5]]`) = current file. Duplicate defs within a tier count as multiple matches (ambiguous); explicit path picks first. Resolution carries raw/kind; to_link_entry omits target/range/candidates when absent; ambiguous has candidates and no target.
