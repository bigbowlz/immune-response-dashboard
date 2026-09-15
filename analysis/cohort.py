"""Cohort definitions and SQL over the raw tables.

Standard library only: this module is imported by both the pipeline and the API.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping

DEFAULT_COHORT: dict[str, object] = {"condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC"}
BASELINE_COHORT: dict[str, object] = {**DEFAULT_COHORT, "time_from_treatment_start": 0}

FILTER_COLUMNS: dict[str, str] = {
    "condition": "subjects.condition",
    "treatment": "subjects.treatment",
    "sample_type": "samples.sample_type",
    "project": "subjects.project",
    "time_from_treatment_start": "samples.time_from_treatment_start",
}

BREAKDOWN_COLUMNS: dict[str, str] = {
    "project": "subjects.project",
    "response": "subjects.response",
    "sex": "subjects.sex",
    "time_from_treatment_start": "samples.time_from_treatment_start",
}

SAMPLE_COLUMNS: tuple[str, ...] = (
    "sample", "subject", "project", "condition", "treatment",
    "sample_type", "time_from_treatment_start", "response", "sex",
)

_SAMPLE_COLUMN_SQL: dict[str, str] = {
    "sample": "samples.sample",
    "subject": "samples.subject",
    "project": "subjects.project",
    "condition": "subjects.condition",
    "treatment": "subjects.treatment",
    "sample_type": "samples.sample_type",
    "time_from_treatment_start": "samples.time_from_treatment_start",
    "response": "subjects.response",
    "sex": "subjects.sex",
}
_SAMPLE_SELECT = ", ".join(f"{sql} AS {name}" for name, sql in _SAMPLE_COLUMN_SQL.items())

_FROM_SAMPLES = "FROM samples JOIN subjects ON subjects.subject = samples.subject"


def build_where(filters: Mapping[str, object]) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    for key, value in filters.items():
        column = FILTER_COLUMNS[key]  # KeyError on unknown filter is intentional
        if value is None:
            continue
        clauses.append(f"{column} = ?")
        params.append(value)
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", params)


def count_cohort(conn: sqlite3.Connection, filters: Mapping[str, object]) -> dict[str, int]:
    where, params = build_where(filters)
    row = conn.execute(
        f"SELECT COUNT(*) AS n_samples, COUNT(DISTINCT samples.subject) AS n_subjects {_FROM_SAMPLES}{where}",
        params,
    ).fetchone()
    return {"n_samples": row["n_samples"], "n_subjects": row["n_subjects"]}


def breakdown(conn: sqlite3.Connection, filters: Mapping[str, object], by: str) -> list[dict]:
    column = BREAKDOWN_COLUMNS[by]
    where, params = build_where(filters)
    total = count_cohort(conn, filters)["n_samples"]
    rows = conn.execute(
        f"SELECT {column} AS category, COUNT(*) AS n_samples, COUNT(DISTINCT samples.subject) AS n_subjects "
        f"{_FROM_SAMPLES}{where} GROUP BY {column} ORDER BY ({column} IS NULL), {column}",
        params,
    ).fetchall()
    return [
        {
            "category": "unknown" if r["category"] is None else r["category"],
            "n_samples": r["n_samples"],
            "n_subjects": r["n_subjects"],
            "pct_samples": round(r["n_samples"] / total * 100, 2) if total else 0.0,
        }
        for r in rows
    ]


def cohort_options(conn: sqlite3.Connection) -> dict[str, list]:
    """Distinct values for every cohort filter, in FILTER_COLUMNS order, each sorted ascending."""
    options: dict[str, list] = {}
    for key, column in FILTER_COLUMNS.items():
        values = [r[0] for r in conn.execute(f"SELECT DISTINCT {column} {_FROM_SAMPLES} ORDER BY {column}")]
        if key == "time_from_treatment_start":
            values = [int(v) for v in values]
        options[key] = values
    return options


def response_points(conn: sqlite3.Connection, filters: Mapping[str, object]) -> list[sqlite3.Row]:
    """Per-sample percentages for samples with a recorded response, from the pipeline's sample_summary table.

    `filters` is a mapping over `FILTER_COLUMNS` keys; a `None` value (or an absent key) leaves that
    filter unapplied.
    """
    where, params = build_where(filters)
    response_clause = "subjects.response IN ('yes', 'no')"
    where_sql = f"{where} AND {response_clause}" if where else f" WHERE {response_clause}"
    return conn.execute(
        "SELECT sample_summary.sample AS sample, samples.subject AS subject, "
        "sample_summary.population AS population, samples.time_from_treatment_start AS time_from_treatment_start, "
        "subjects.response AS response, sample_summary.percentage AS percentage, "
        "sample_summary.count AS count, sample_summary.total_count AS total_count "
        "FROM sample_summary "
        "JOIN samples ON samples.sample = sample_summary.sample "
        "JOIN subjects ON subjects.subject = samples.subject"
        f"{where_sql} "
        "ORDER BY sample_summary.population, samples.time_from_treatment_start, subjects.response, sample_summary.sample",
        params,
    ).fetchall()


def missing_response_count(conn: sqlite3.Connection, filters: Mapping[str, object]) -> int:
    """Count of matching samples whose subject has no recorded response."""
    where, params = build_where(filters)
    where_sql = f"{where} AND subjects.response IS NULL" if where else " WHERE subjects.response IS NULL"
    row = conn.execute(f"SELECT COUNT(*) AS n {_FROM_SAMPLES}{where_sql}", params).fetchone()
    return row["n"]


def count_samples(conn: sqlite3.Connection, filters: Mapping[str, object]) -> int:
    where, params = build_where(filters)
    row = conn.execute(f"SELECT COUNT(*) AS n {_FROM_SAMPLES}{where}", params).fetchone()
    return row["n"]


def list_samples(
    conn: sqlite3.Connection,
    filters: Mapping[str, object],
    sort: str = "sample",
    direction: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    if sort not in SAMPLE_COLUMNS:
        raise ValueError(f"invalid sort column: {sort!r}")
    if direction not in ("asc", "desc"):
        raise ValueError(f"invalid sort direction: {direction!r}")
    where, params = build_where(filters)
    sort_column = _SAMPLE_COLUMN_SQL[sort]
    direction_sql = "ASC" if direction == "asc" else "DESC"
    # NULLs (only possible for `response`) sort last regardless of direction.
    order = f"ORDER BY ({sort_column} IS NULL) ASC, {sort_column} {direction_sql}, samples.sample ASC"
    rows = conn.execute(
        f"SELECT {_SAMPLE_SELECT} {_FROM_SAMPLES}{where} {order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]
