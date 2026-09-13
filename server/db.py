"""Read-only SQLite access for the API."""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator

from fastapi import HTTPException

from analysis.schema import resolve_db_path


def get_conn() -> Iterator[sqlite3.Connection]:
    path = resolve_db_path()
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"Database {path.name} not found. Run `make pipeline` first.")
    # immutable=1 skips locking and refuses to create -shm/-wal files, which Vercel's read-only filesystem
    # would reject; locally the filesystem is writable, so mode=ro alone still respects SQLite's locking,
    # letting a request made during `make pipeline` wait rather than read a half-written database.
    mode = "ro&immutable=1" if os.environ.get("VERCEL") else "ro"
    conn = sqlite3.connect(f"file:{path}?mode={mode}", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
