"""Create the SQLite database and load cell-count.csv into it.

Usage: python load_data.py
Takes no arguments. Writes cell_counts.db in the repository root.
Environment overrides: CELL_COUNTS_DB (output path), CELL_COUNTS_CSV (input path).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis import schema  # noqa: E402
from analysis.loader import load_csv  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        stream = sys.stdout if args[0] in ("-h", "--help") else sys.stderr
        print(__doc__.strip(), file=stream)
        return 0 if stream is sys.stdout else 2
    db_path = schema.resolve_db_path()
    csv_path = schema.resolve_csv_path()
    if not csv_path.exists():
        print(
            f"Input file not found: {csv_path}\n"
            "load_data.py expects cell-count.csv in the repository root "
            "(or set CELL_COUNTS_CSV to its path).",
            file=sys.stderr,
        )
        return 1
    conn = schema.connect(db_path)
    try:
        schema.create_schema(conn)
        report = load_csv(csv_path, conn)
    finally:
        conn.close()
    print(f"Loaded {report.rows} rows: {report.samples} samples from {report.subjects} subjects into {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
