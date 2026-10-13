import hashlib
import json

import pytest

from readcode import kbio


def test_atomic_json_format(tmp_path):
    p = tmp_path / "a" / "b.json"
    kbio.atomic_write_json(p, {"z": 1, "a": "ñandú"})
    text = p.read_text(encoding="utf-8")
    assert text == '{\n  "z": 1,\n  "a": "ñandú"\n}\n'
    assert kbio.read_json(p) == {"z": 1, "a": "ñandú"}
    assert list(json.loads(text)) == ["z", "a"]


def test_atomic_write_leaves_no_temp_and_replaces(tmp_path):
    p = tmp_path / "f.txt"
    kbio.atomic_write_text(p, "one\r\n")
    kbio.atomic_write_text(p, "two\r\n")
    assert p.read_bytes() == b"two\r\n"
    assert [x.name for x in tmp_path.iterdir()] == ["f.txt"]


def test_atomic_write_failure_keeps_original(tmp_path):
    p = tmp_path / "f.json"
    kbio.atomic_write_json(p, {"ok": 1})
    with pytest.raises(TypeError):
        kbio.atomic_write_json(p, {"bad": object()})
    assert kbio.read_json(p) == {"ok": 1}
    assert [x.name for x in tmp_path.iterdir()] == ["f.json"]


def test_hash_and_paths(tmp_path):
    h = kbio.sha256_hex(b"abc")
    assert h == hashlib.sha256(b"abc").hexdigest()
    sd = kbio.study_dir(tmp_path, "s")
    assert sd == tmp_path / "s"
    assert kbio.blob_path(sd, h) == sd / "blobs" / h[:2] / f"{h}.txt"
    assert kbio.snapshot_dir(sd, "a" * 40) == sd / "snapshots" / ("a" * 40)


# Lines with characters that str.splitlines() treats as breaks but readcode does not.
ODD = "a\fb\nc\x85d\ne\u2028f\ng\rh\r\ni\n".encode("utf-8")


def test_blob_lines_splits_only_on_newline():
    lines = kbio.blob_lines(ODD)
    assert lines == ["a\fb", "c\x85d", "e\u2028f", "g\rh", "i"]
    assert len(lines) == ODD.count(b"\n")
    assert len(ODD.decode("utf-8").splitlines()) > len(lines)  # what we must not do
    assert kbio.blob_lines(b"") == []
    assert kbio.blob_lines(b"\n") == [""]
    assert kbio.blob_lines(b"x") == ["x"] and kbio.blob_lines(b"x\r\ny") == ["x", "y"]
    assert kbio.blob_lines(b"\xff\n") == ["\ufffd"]
