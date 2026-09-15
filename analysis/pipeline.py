"""Run the analysis and write every result table into the database.

Usage: python -m analysis.pipeline   (after python load_data.py; takes no arguments)
Environment overrides: CELL_COUNTS_DB (database path), CELL_COUNTS_CSV (input used for the provenance hash).
"""
from __future__ import annotations

import hashlib
import itertools
import math
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

COHORT_DIMENSIONS = ("condition", "treatment", "sample_type", "project")
DAYS = (0, 7, 14)

NO_RESPONSES_REASON = "no recorded responses in this cohort"

STATS_COLUMNS = [
    "condition", "treatment", "sample_type", "project", "timepoints",
    "population", "time_from_treatment_start", "n_responders", "n_nonresponders",
    "median_responders", "median_nonresponders", "u_statistic", "p_raw", "p_adj",
    "effect_size", "significant", "status", "reason",
]
STRATA_COLUMNS = [
    "condition", "treatment", "sample_type", "project", "timepoints",
    "n_samples", "n_subjects", "n_missing_response", "n_tests",
]
POINT_COLUMNS = ["sample", "subject", "population", "time_from_treatment_start", "response", "percentage", "count", "total_count"]


@dataclass(frozen=True)
class PipelineReport:
    summary_rows: int
    stats_rows: int
    strata: int
    default_n_tests: int
    default_min_p_adj: float
    significant: tuple[tuple[str, str, str, str, str, str, int], ...]  # default-cohort families only
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
    """sqlite3 does not accept numpy scalars, and a float NaN must become a NULL, not a stored NaN."""
    value = value.item() if hasattr(value, "item") else value
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


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


def enumerate_cohort_keys(conn: sqlite3.Connection) -> list[dict]:
    """Every selectable (condition, treatment, sample_type, project) key: product of {'all'} union
    each filter's distinct values, in `cohort_options` order. 4 x 4 x 3 x 4 = 192 keys."""
    options = cohort.cohort_options(conn)
    axes = [["all", *(str(v) for v in options[dim])] for dim in COHORT_DIMENSIONS]
    return [dict(zip(COHORT_DIMENSIONS, combo)) for combo in itertools.product(*axes)]


def _key_filters(key: dict) -> dict:
    return {dim: (None if key[dim] == "all" else key[dim]) for dim in COHORT_DIMENSIONS}


def _family_frame(key: dict, family: str, cells: pd.DataFrame) -> pd.DataFrame:
    """`cells` (a full or day-sliced `compare_cells` frame) with BH applied within the family and the
    cohort key columns attached, ready to append to the combined `response_stats` frame."""
    adjusted = stats.adjust_family(cells)
    for dim in COHORT_DIMENSIONS:
        adjusted[dim] = key[dim]
    adjusted["timepoints"] = family
    return adjusted[STATS_COLUMNS]


def write_response_stats(conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Precompute every population x timepoint test for every selectable cohort key.

    Raw cells (one Mann-Whitney U per population x timepoint) are computed once per key with
    `stats.compare_cells`. The four correction families for that key ('all' plus one per timepoint)
    are then derived from that same frame, each with its own BH pass, never rerunning the U test.
    """
    stats_frames: list[pd.DataFrame] = []
    strata_records: list[dict] = []
    for key in enumerate_cohort_keys(conn):
        filters = _key_filters(key)
        points = pd.DataFrame([dict(r) for r in cohort.response_points(conn, filters)], columns=POINT_COLUMNS)
        cells = stats.compare_cells(points, DAYS)

        cohort_count = cohort.count_cohort(conn, filters)
        missing_all = cohort.missing_response_count(conn, filters)
        if cohort_count["n_samples"] > 0 and missing_all == cohort_count["n_samples"]:
            # Safe to apply to every timepoint slice of `cells`, not just the 'all' family: response is
            # subject-level, not sample-level, and every subject has a sample at every timepoint, so a
            # cohort with no recorded responses overall has none at any single timepoint either.
            cells = cells.copy()
            cells["reason"] = NO_RESPONSES_REASON

        key_columns = {dim: key[dim] for dim in COHORT_DIMENSIONS}
        stats_frames.append(_family_frame(key, "all", cells))
        strata_records.append({
            **key_columns, "timepoints": "all",
            "n_samples": cohort_count["n_samples"], "n_subjects": cohort_count["n_subjects"],
            "n_missing_response": missing_all, "n_tests": stats.family_size(cells),
        })

        for day in DAYS:
            day_cells = cells[cells["time_from_treatment_start"] == day].reset_index(drop=True)
            stats_frames.append(_family_frame(key, str(day), day_cells))
            day_filters = {**filters, "time_from_treatment_start": day}
            day_count = cohort.count_cohort(conn, day_filters)
            strata_records.append({
                **key_columns, "timepoints": str(day),
                "n_samples": day_count["n_samples"], "n_subjects": day_count["n_subjects"],
                "n_missing_response": cohort.missing_response_count(conn, day_filters),
                "n_tests": stats.family_size(day_cells),
            })

    stats_combined = pd.concat(stats_frames, ignore_index=True)[STATS_COLUMNS]
    strata_combined = pd.DataFrame.from_records(strata_records, columns=STRATA_COLUMNS)
    _write(conn, "response_stats", stats_combined)
    _write(conn, "response_strata", strata_combined)
    return stats_combined, strata_combined


def write_cohort_summary(conn: sqlite3.Connection) -> None:
    total = cohort.count_cohort(conn, cohort.BASELINE_COHORT)
    rows = [("total", "all", total["n_samples"], total["n_subjects"], 100.0)]
    for by in ("project", "response", "sex"):
        for r in cohort.breakdown(conn, cohort.BASELINE_COHORT, by):
            rows.append((by, str(r["category"]), r["n_samples"], r["n_subjects"], r["pct_samples"]))
    with conn:
        conn.execute("DELETE FROM cohort_summary")
        conn.executemany("INSERT INTO cohort_summary VALUES (?, ?, ?, ?, ?)", rows)


def run(db_path: Path | None = None, csv_path: Path | None = None) -> PipelineReport:
    conn = schema.connect(db_path)
    try:
        summary_rows = write_sample_summary(conn)
        stats_frame, strata_frame = write_response_stats(conn)
        write_cohort_summary(conn)
        meta = write_pipeline_meta(conn, csv_path or schema.resolve_csv_path())
    finally:
        conn.close()

    default_mask = (
        (stats_frame["condition"] == cohort.DEFAULT_COHORT["condition"])
        & (stats_frame["treatment"] == cohort.DEFAULT_COHORT["treatment"])
        & (stats_frame["sample_type"] == cohort.DEFAULT_COHORT["sample_type"])
        & (stats_frame["project"] == "all")
    )
    default_rows = stats_frame[default_mask]
    default_all = default_rows[default_rows["timepoints"] == "all"]
    default_ok = default_all[default_all["status"] == "ok"]
    default_n_tests = int(len(default_ok))
    default_min_p_adj = float(default_ok["p_adj"].min())
    significant = tuple(
        (r.condition, r.treatment, r.sample_type, r.project, r.timepoints, r.population, int(r.time_from_treatment_start))
        for r in default_rows.itertuples() if r.significant
    )
    return PipelineReport(
        summary_rows=summary_rows,
        stats_rows=len(stats_frame),
        strata=len(strata_frame),
        default_n_tests=default_n_tests,
        default_min_p_adj=default_min_p_adj,
        significant=significant,
        generated_at=meta["generated_at"],
    )


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
    if report.significant:
        for condition, treatment, sample_type, project, timepoints, population, day in report.significant:
            print(
                f"  significant at adjusted p < {stats.ALPHA}: {population} at day {day} "
                f"({condition}/{treatment}/{sample_type}/{project}, family {timepoints})"
            )
    else:
        print(f"  default cohort: no population reaches adjusted p < {stats.ALPHA} in any family")
    print(
        f"response_stats: {report.stats_rows} rows over {report.strata} strata; "
        f"default cohort: {report.default_n_tests} tests, smallest adjusted p {report.default_min_p_adj:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
