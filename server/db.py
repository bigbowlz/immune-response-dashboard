"""Read-only SQLite access for the API."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import HTTPException

from analysis.schema import resolve_db_path


def get_conn() -> Iterator[sqlite3.Connection]:
    path = resolve_db_path()
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"Database {path.name} not found. Run `make pipeline` first.")
    # immutable=1: no lock or -shm files, which a read-only filesystem (Vercel) would refuse to create.
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
