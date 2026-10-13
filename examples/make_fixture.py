"""Builds a small, deterministic multi-language git repo used by readcode tests and demos.

Usage: python examples/make_fixture.py [dest]   (default: examples/fixture-repo)
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

DEFAULT_DEST = Path(__file__).resolve().parent / "fixture-repo"

COMMIT1_DATE = "2026-01-10T10:00:00+00:00"
COMMIT2_DATE = "2026-01-11T10:00:00+00:00"

FILES_V1: dict[str, str] = {
    "README.md": "# Fixture app\n\nSmall multi-language app used to test readcode.\n",
    ".gitignore": "*.log\n.env\n",
    "package-lock.json": '{\n  "name": "fixture",\n  "lockfileVersion": 3\n}\n',
    "node_modules/junk.js": "module.exports = function junk() { return 1; };\n",
    "app/main.py": '''from app.services import billing, auth


def main():
    user = auth.process({"name": "ana"})
    total = billing.process(user, [10, 20, 30])
    print(f"total={total}")


if __name__ == "__main__":
    main()
''',
    "app/services/billing.py": '''from app.models import Invoice


def compute_total(items):
    return sum(items)


def process(user, items):
    invoice = Invoice(user["name"], compute_total(items))
    return invoice.total
''',
    "app/services/auth.py": '''def hash_token(token):
    return str(hash(token))


def process(request):
    request["token"] = hash_token(request["name"])
    return request
''',
    "app/models.py": '''class Invoice:
    def __init__(self, owner, total):
        self.owner = owner
        self.total = total

    def describe(self):
        return f"{self.owner}: {self.total}"
''',
    "web/src/types.ts": '''export interface Invoice {
  owner: string;
  total: number;
}

export interface ApiResponse<T> {
  ok: boolean;
  data: T;
}
''',
    "web/src/api.ts": '''import { ApiResponse, Invoice } from "./types";

export async function fetchInvoice(id: string): Promise<ApiResponse<Invoice>> {
  const res = await fetch(`/api/invoices/${id}`);
  return res.json();
}
''',
    "web/src/index.ts": '''import { fetchInvoice } from "./api";

fetchInvoice("1").then((r) => console.log(r.data.total));
''',
    "worker/main.go": '''package main

import "fmt"

func main() {
	q := NewQueue()
	q.Push("job-1")
	fmt.Println(q.Pop())
}
''',
    "worker/queue.go": '''package main

type Queue struct {
	items []string
}

func NewQueue() *Queue {
	return &Queue{}
}

func (q *Queue) Push(item string) {
	q.items = append(q.items, item)
}

func (q *Queue) Pop() string {
	item := q.items[0]
	q.items = q.items[1:]
	return item
}
''',
    "db/schema.sql": '''CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE invoices (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  total INTEGER NOT NULL
);
''',
    "db/queries.sql": '''SELECT * FROM invoices WHERE user_id = 1;
SELECT name FROM users ORDER BY name;
''',
}

BINARY_FILES: dict[str, bytes] = {
    "assets/logo.bin": b"\x89LOGO\x00\x00\x01\x02\x00\xff\x00data\x00",
}

BILLING_V2_SUFFIX = '''

def refund(user, amount):
    invoice = Invoice(user["name"], -amount)
    return invoice.total
'''

REFUNDS_PY = '''from app.services.billing import refund


def process_refund(user, amount):
    return refund(user, amount)
'''

API_TS_V2_SUFFIX = '''
export async function refundInvoice(id: string): Promise<ApiResponse<Invoice>> {
  const res = await fetch(`/api/invoices/${id}/refund`, { method: "POST" });
  return res.json();
}
'''


def _write(root: Path, rel: str, data: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)  # bytes: no newline translation, stable blobs


def _git(dest: Path, env: dict[str, str], *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=dest, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _on_rm_error(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def build_fixture(dest: Path) -> tuple[str, str]:
    """(Re)create the fixture repo at dest. Returns (sha1, sha2). Deterministic."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest, onerror=_on_rm_error)
    dest.mkdir(parents=True)

    base_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture Author",
        "GIT_AUTHOR_EMAIL": "fixture@example.com",
        "GIT_COMMITTER_NAME": "Fixture Author",
        "GIT_COMMITTER_EMAIL": "fixture@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def env_for(date: str) -> dict[str, str]:
        return {**base_env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}

    env = env_for(COMMIT1_DATE)
    _git(dest, env, "init", "-q", "-b", "main")
    _git(dest, env, "config", "core.autocrlf", "false")
    _git(dest, env, "config", "commit.gpgsign", "false")

    for rel, content in FILES_V1.items():
        _write(dest, rel, content)
    for rel, blob in BINARY_FILES.items():
        _write(dest, rel, blob)
    # node_modules is not in the fixture's .gitignore, so it is committed on purpose
    _git(dest, env, "add", "-A")
    _git(dest, env, "commit", "-q", "-m", "initial")
    sha1 = _git(dest, env, "rev-parse", "HEAD")

    env = env_for(COMMIT2_DATE)
    billing = dest / "app/services/billing.py"
    _write(dest, "app/services/billing.py", billing.read_text(encoding="utf-8") + BILLING_V2_SUFFIX)
    _write(dest, "app/services/refunds.py", REFUNDS_PY)
    (dest / "db/queries.sql").unlink()
    api = dest / "web/src/api.ts"
    _write(dest, "web/src/api.ts", api.read_text(encoding="utf-8") + API_TS_V2_SUFFIX)
    _git(dest, env, "add", "-A")
    _git(dest, env, "commit", "-q", "-m", "feature: refunds")
    sha2 = _git(dest, env, "rev-parse", "HEAD")
    return sha1, sha2


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DEST
    s1, s2 = build_fixture(target)
    print(f"repo: {target}")
    print(f"sha1: {s1}")
    print(f"sha2: {s2}")
