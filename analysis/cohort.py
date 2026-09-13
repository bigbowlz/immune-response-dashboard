"""Cohort definitions and SQL over the raw tables.

Standard library only: this module is imported by both the pipeline and the API.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping

RESPONSE_COHORT: dict[str, object] = {"condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC"}
BASELINE_COHORT: dict[str, object] = {**RESPONSE_COHORT, "time_from_treatment_start": 0}

FILTER_COLUMNS: dict[str, str] = {
    "condition": "subjects.condition",
    "treatment": "subjects.treatment",
    "sample_type": "samples.sample_type",
    "time_from_treatment_start": "samples.time_from_treatment_start",
}

BREAKDOWN_COLUMNS: dict[str, str] = {
    "project": "subjects.project",
    "response": "subjects.response",
    "sex": "subjects.sex",
    "time_from_treatment_start": "samples.time_from_treatment_start",
}

FORM_QUESTION = (
    "Considering melanoma males of all sample and treatment types, "
    "what is the average number of B cells for responders at time=0?"
)

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
        f"{_FROM_SAMPLES}{where} GROUP BY {column} ORDER BY {column}",
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


def filter_options(conn: sqlite3.Connection) -> dict[str, list]:
    return {
        key: [r[0] for r in conn.execute(f"SELECT DISTINCT {column} {_FROM_SAMPLES} ORDER BY {column}")]
        for key, column in FILTER_COLUMNS.items()
    }


def form_answer(conn: sqlite3.Connection) -> tuple[int, float]:
    """Mean b_cell count for melanoma, male, responder samples at time 0. No sample_type or treatment filter."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, AVG(cell_counts.count) AS mean_count "
        "FROM cell_counts "
        "JOIN samples ON samples.sample = cell_counts.sample "
        "JOIN subjects ON subjects.subject = samples.subject "
        "WHERE cell_counts.population = 'b_cell' AND subjects.condition = 'melanoma' "
        "AND subjects.sex = 'M' AND subjects.response = 'yes' AND samples.time_from_treatment_start = 0"
    ).fetchone()
    return row["n"], round(row["mean_count"], 2)


def response_cohort_points(conn: sqlite3.Connection, project: str | None = None) -> list[sqlite3.Row]:
    """Per-sample percentages for the Part 3 cohort, from the pipeline's sample_summary table.

    With `project`, only that project's samples (the stratified view)."""
    where, params = build_where(RESPONSE_COHORT)
    project_clause = ""
    if project is not None:
        project_clause = " AND subjects.project = ?"
        params = [*params, project]
    return conn.execute(
        "SELECT sample_summary.sample, samples.subject, subjects.project, sample_summary.population, "
        "samples.time_from_treatment_start, subjects.response, sample_summary.percentage "
        "FROM sample_summary "
        "JOIN samples ON samples.sample = sample_summary.sample "
        "JOIN subjects ON subjects.subject = samples.subject "
        f"{where} AND subjects.response IN ('yes', 'no'){project_clause} "
        "ORDER BY sample_summary.population, samples.time_from_treatment_start, subjects.response, sample_summary.sample",
        params,
    ).fetchall()


def response_projects(conn: sqlite3.Connection) -> list[str]:
    """Projects that contribute samples to the Part 3 cohort, sorted."""
    where, params = build_where(RESPONSE_COHORT)
    rows = conn.execute(
        f"SELECT DISTINCT subjects.project {_FROM_SAMPLES}{where} AND subjects.response IN ('yes', 'no') ORDER BY subjects.project",
        params,
    ).fetchall()
    return [r[0] for r in rows]
