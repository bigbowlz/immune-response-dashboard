"""Run the analysis and write every result table into the database.

Usage: python -m analysis.pipeline   (after python load_data.py; takes no arguments)
Environment overrides: CELL_COUNTS_DB (database path), CELL_COUNTS_CSV (input used for the provenance hash).
"""
from __future__ import annotations

import hashlib
import platform
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - exercised only when make setup was skipped
    print(
        "pandas is not installed. Run `make setup` (or `pip install -r requirements-pipeline.txt`) first.",
        file=sys.stderr,
    )
    raise SystemExit(1)

from analysis import cohort, schema, stats


@dataclass(frozen=True)
class PipelineReport:
    summary_rows: int
    stats_rows: int
    significant: tuple[tuple[str, str, int], ...]  # (project stratum, population, timepoint)
    form_answer: tuple[int, float]
    generated_at: str = ""


def _write(conn: sqlite3.Connection, table: str, frame: pd.DataFrame) -> None:
    placeholders = ", ".join("?" for _ in frame.columns)
    columns = ", ".join(frame.columns)
    with conn:
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            [tuple(_native(v) for v in row) for row in frame.itertuples(index=False, name=None)],
        )


def _native(value):
    """sqlite3 does not accept numpy scalars; convert them to Python numbers."""
    return value.item() if hasattr(value, "item") else value


def write_sample_summary(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT sample, population, count FROM cell_counts").fetchall()
    counts = pd.DataFrame([tuple(r) for r in rows], columns=["sample", "population", "count"])
    summary = stats.compute_sample_summary(counts)
    _write(conn, "sample_summary", summary)
    return len(summary)


def write_pipeline_meta(conn: sqlite3.Connection, csv_path: Path) -> dict[str, str]:
    """Provenance for the run so the dashboard and README can say which input produced the numbers."""
    import scipy

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "csv_sha256": digest,
        "csv_rows": str(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]),
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
        "scipy_version": scipy.__version__,
    }
    with conn:
        conn.execute("DELETE FROM pipeline_meta")
        conn.executemany("INSERT INTO pipeline_meta VALUES (?, ?)", meta.items())
    return meta


POINT_COLUMNS = ["sample", "subject", "project", "population", "time_from_treatment_start", "response", "percentage"]


def write_response_stats(conn: sqlite3.Connection) -> pd.DataFrame:
    """One stratum for the whole cohort ('all') plus one per project. BH is applied within each stratum
    because each stratum is its own family of 15 tests that a reader looks at on its own."""
    points = pd.DataFrame([dict(r) for r in cohort.response_cohort_points(conn)], columns=POINT_COLUMNS)
    strata = [("all", points)] + [(project, points[points["project"] == project]) for project in cohort.response_projects(conn)]
    frames = []
    for project, subset in strata:
        result = stats.compare_response_groups(subset)
        result.insert(0, "project", project)
        frames.append(result)
    combined = pd.concat(frames, ignore_index=True)
    _write(conn, "response_stats", combined)
    return combined


def write_cohort_summary(conn: sqlite3.Connection) -> None:
    total = cohort.count_cohort(conn, cohort.BASELINE_COHORT)
    rows = [("total", "all", total["n_samples"], total["n_subjects"], 100.0)]
    for by in ("project", "response", "sex"):
        for r in cohort.breakdown(conn, cohort.BASELINE_COHORT, by):
            rows.append((by, str(r["category"]), r["n_samples"], r["n_subjects"], r["pct_samples"]))
    with conn:
        conn.execute("DELETE FROM cohort_summary")
        conn.executemany("INSERT INTO cohort_summary VALUES (?, ?, ?, ?, ?)", rows)


def write_form_answer(conn: sqlite3.Connection) -> tuple[int, float]:
    n, mean = cohort.form_answer(conn)
    with conn:
        conn.execute("DELETE FROM form_answer")
        conn.execute("INSERT INTO form_answer VALUES (?, ?, ?)", (cohort.FORM_QUESTION, n, mean))
    return n, mean


def run(db_path: Path | None = None, csv_path: Path | None = None) -> PipelineReport:
    conn = schema.connect(db_path)
    try:
        summary_rows = write_sample_summary(conn)
        result = write_response_stats(conn)
        write_cohort_summary(conn)
        answer = write_form_answer(conn)
        meta = write_pipeline_meta(conn, csv_path or schema.resolve_csv_path())
    finally:
        conn.close()
    significant = tuple(
        (str(r.project), str(r.population), int(r.time_from_treatment_start))
        for r in result.itertuples() if r.significant
    )
    return PipelineReport(summary_rows, len(result), significant, answer, meta["generated_at"])


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        stream = sys.stdout if args[0] in ("-h", "--help") else sys.stderr
        print(__doc__.strip(), file=stream)
        return 0 if stream is sys.stdout else 2
    db_path = schema.resolve_db_path()
    if not db_path.exists():
        print(f"{db_path} does not exist. Run `python load_data.py` first (make pipeline does both).", file=sys.stderr)
        return 1
    report = run(db_path)
    print(f"sample_summary: {report.summary_rows} rows")
    print(f"response_stats: {report.stats_rows} tests (Mann-Whitney U per population per timepoint, BH-adjusted within each project stratum)")
    if report.significant:
        for project, population, day in report.significant:
            print(f"  significant at adjusted p < {stats.ALPHA}: {population} at day {day} (project {project})")
    else:
        print(f"  no population reaches adjusted p < {stats.ALPHA} in any stratum")
    n, mean = report.form_answer
    print(f"Form answer: mean b_cell = {mean:.2f} (n = {n})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
