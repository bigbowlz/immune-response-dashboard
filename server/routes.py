"""API routes. Every endpoint reads tables the pipeline wrote; nothing is computed here beyond SQL."""
from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from analysis import cohort
from analysis.schema import RAW_TABLES, RESULT_TABLES, resolve_db_path
from server.db import get_conn

# Mirrors analysis.stats.ALPHA. Kept as a literal so the API never imports pandas/scipy.
ALPHA = 0.05

router = APIRouter(prefix="/api")
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

SUMMARY_COLUMNS = ("sample", "total_count", "population", "count", "percentage")
SortColumn = Literal["sample", "total_count", "population", "count", "percentage"]
SortDir = Literal["asc", "desc"]
Search = Annotated[str | None, Query(max_length=100, description="Substring match on sample or population")]
POPULATION_ORDER = "CASE population WHEN 'b_cell' THEN 0 WHEN 'cd8_t_cell' THEN 1 WHEN 'cd4_t_cell' THEN 2 WHEN 'nk_cell' THEN 3 ELSE 4 END"

# The four columns that identify a selectable cohort key in response_stats/response_strata
# (the fifth filter, time_from_treatment_start, is the correction family instead).
COHORT_KEY_COLUMNS = ("condition", "treatment", "sample_type", "project")
SampleSortColumn = Literal[cohort.SAMPLE_COLUMNS]


@router.get("/health")
def health(conn: Conn) -> dict:
    """Row counts per table plus the provenance written by the last pipeline run."""
    try:
        tables = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in RAW_TABLES + RESULT_TABLES}
        meta = dict(conn.execute("SELECT key, value FROM pipeline_meta").fetchall())
    except sqlite3.OperationalError:
        # A table RESULT_TABLES expects (e.g. pipeline_meta) is missing: an older database, wrong schema.
        raise HTTPException(status_code=503, detail="Database schema is out of date. Run make pipeline, then reload.") from None
    if tables["pipeline_meta"] == 0 or any(tables[t] == 0 for t in RESULT_TABLES):
        # The pipeline writes pipeline_meta last, so any empty result table means a run never finished.
        raise HTTPException(status_code=503, detail="Pipeline output is incomplete. Run make pipeline, then reload.")
    return {"status": "ok", "db_path": resolve_db_path().name, "tables": tables, "meta": meta}


def _frequencies_sql(search: str | None, sort: SortColumn, direction: SortDir) -> tuple[str, str, list]:
    """Returns (where_clause, order_clause, params). sort and direction are Literal-validated by FastAPI."""
    where, params = "", []
    if search:
        # Escape LIKE wildcards so a search for "_" or "%" is literal.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where = " WHERE sample LIKE ? ESCAPE '\\' OR population LIKE ? ESCAPE '\\'"
        params = [f"%{escaped}%", f"%{escaped}%"]
    primary = POPULATION_ORDER if sort == "population" else sort
    order = f" ORDER BY {primary} {direction.upper()}, sample ASC, {POPULATION_ORDER} ASC"
    return where, order, params


@router.get("/frequencies")
def frequencies(
    conn: Conn,
    search: Search = None,
    sort: SortColumn = "sample",
    dir: SortDir = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Part 2 summary table, one page at a time. Sorting and searching happen in SQL."""
    where, order, params = _frequencies_sql(search, sort, dir)
    total = conn.execute(f"SELECT COUNT(*) FROM sample_summary{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT sample, total_count, population, count, percentage FROM sample_summary{where}{order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/frequencies.csv")
def frequencies_csv(conn: Conn, search: Search = None, sort: SortColumn = "sample", dir: SortDir = "asc") -> StreamingResponse:
    """Every matching row of the Part 2 table as CSV, in the same order the table shows."""
    where, order, params = _frequencies_sql(search, sort, dir)
    # Materialise before returning: the connection dependency closes when the handler returns,
    # so the generator must not touch the cursor. 52,500 tuples is a few MB, fine.
    rows = [tuple(r) for r in conn.execute(
        f"SELECT sample, total_count, population, count, percentage FROM sample_summary{where}{order}", params
    ).fetchall()]

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(SUMMARY_COLUMNS)
        yield buffer.getvalue()
        for start in range(0, len(rows), 2000):
            buffer.seek(0)
            buffer.truncate()
            writer.writerows(rows[start:start + 2000])
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cell_population_frequencies.csv"'},
    )


@dataclass(frozen=True)
class CohortFilters:
    """The five cohort filters, in three shapes used by different callers.

    `filters`: mapping for `cohort.build_where`/`cohort.breakdown` etc. -- 'all' becomes None and the
    timepoint becomes an int.
    `key`: the five request strings as sent (with 'all' kept literal), for `response_stats` lookups and
    for echoing back in a response body.
    `family`: `key["time_from_treatment_start"]` -- 'all' or the day string, the response_stats/
    response_strata correction-family column.
    """

    filters: dict[str, object]
    key: dict[str, str]
    family: str


def cohort_filters(
    conn: Conn,
    condition: Annotated[str, Query(description="'all' or a condition from /api/cohort/options")] = "melanoma",
    treatment: Annotated[str, Query(description="'all' or a treatment from /api/cohort/options")] = "miraclib",
    sample_type: Annotated[str, Query(description="'all' or a sample type from /api/cohort/options")] = "PBMC",
    project: Annotated[str, Query(description="'all' or a project from /api/cohort/options")] = "all",
    time_from_treatment_start: Annotated[str, Query(description="'all' or a timepoint from /api/cohort/options")] = "all",
) -> CohortFilters:
    options = cohort.cohort_options(conn)
    raw = {
        "condition": condition,
        "treatment": treatment,
        "sample_type": sample_type,
        "project": project,
        "time_from_treatment_start": time_from_treatment_start,
    }
    filters: dict[str, object] = {}
    for name, value in raw.items():
        allowed = options[name]
        if value == "all":
            filters[name] = None
            continue
        if name == "time_from_treatment_start":
            try:
                parsed: object = int(value)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"{name} must be 'all' or one of {allowed}") from None
        else:
            parsed = value
        if parsed not in allowed:
            raise HTTPException(status_code=422, detail=f"{name} must be 'all' or one of {allowed}")
        filters[name] = parsed
    # Derived from the parsed value, not the raw query string: "07" and "7" both parse to the int 7,
    # so both must land in the same response_stats/response_strata family, "7".
    timepoint = filters["time_from_treatment_start"]
    family = "all" if timepoint is None else str(timepoint)
    return CohortFilters(filters=filters, key=raw, family=family)


Filters = Annotated[CohortFilters, Depends(cohort_filters)]


@router.get("/cohort/options")
def cohort_options(conn: Conn) -> dict:
    """Distinct values for every cohort filter; timepoints as integers."""
    return cohort.cohort_options(conn)


@router.get("/cohort/summary")
def cohort_summary(conn: Conn, filters: Filters) -> dict:
    """Composition of the selected cohort, over the raw tables."""
    counts = cohort.count_cohort(conn, filters.filters)
    breakdowns = {by: cohort.breakdown(conn, filters.filters, by) for by in cohort.BREAKDOWN_COLUMNS}
    return {
        "filters": filters.key,
        "n_samples": counts["n_samples"],
        "n_subjects": counts["n_subjects"],
        "n_missing_response": cohort.missing_response_count(conn, filters.filters),
        "breakdowns": breakdowns,
    }


@router.get("/cohort/stats")
def cohort_stats(conn: Conn, filters: Filters) -> dict:
    """Precomputed response statistics for the selected cohort key and correction family."""
    key_params = [filters.key[column] for column in COHORT_KEY_COLUMNS]
    strata = conn.execute(
        "SELECT n_samples, n_subjects, n_missing_response, n_tests FROM response_strata "
        "WHERE condition = ? AND treatment = ? AND sample_type = ? AND project = ? AND timepoints = ?",
        [*key_params, filters.family],
    ).fetchone()
    if strata is None:
        # Every selectable key x family is precomputed by the pipeline; a miss means the database
        # predates this cohort's key set.
        raise HTTPException(status_code=503, detail="Statistics are not precomputed for this cohort. Run `make pipeline`, then reload.")
    rows = conn.execute(
        "SELECT * FROM response_stats WHERE condition = ? AND treatment = ? AND sample_type = ? AND project = ? AND timepoints = ? "
        f"ORDER BY time_from_treatment_start, {POPULATION_ORDER}",
        [*key_params, filters.family],
    ).fetchall()
    return {
        "filters": filters.key,
        "family": filters.family,
        "rows": [dict(r) for r in rows],
        "alpha": ALPHA,
        "n_tests": strata["n_tests"],
        "n_samples": strata["n_samples"],
        "n_subjects": strata["n_subjects"],
        "n_missing_response": strata["n_missing_response"],
    }


@router.get("/cohort/points")
def cohort_points(conn: Conn, filters: Filters) -> dict:
    """Per-sample percentages for samples with a recorded response, for the boxplots."""
    return {"points": [dict(r) for r in cohort.response_points(conn, filters.filters)]}


@router.get("/cohort/samples")
def cohort_samples(
    conn: Conn,
    filters: Filters,
    sort: SampleSortColumn = "sample",
    dir: SortDir = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    total = cohort.count_samples(conn, filters.filters)
    rows = cohort.list_samples(conn, filters.filters, sort=sort, direction=dir, limit=limit, offset=offset)
    return {"rows": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/cohort/samples.csv")
def cohort_samples_csv(conn: Conn, filters: Filters, sort: SampleSortColumn = "sample", dir: SortDir = "asc") -> StreamingResponse:
    """Every matching sample as CSV, in the same order the table shows."""
    total = cohort.count_samples(conn, filters.filters)
    # `list_samples` already materialises its rows (fetchall) before returning, so this happens
    # before the StreamingResponse below is built and the connection dependency closes.
    rows = cohort.list_samples(conn, filters.filters, sort=sort, direction=dir, limit=max(total, 1), offset=0)
    tuples = [tuple(r[column] for column in cohort.SAMPLE_COLUMNS) for r in rows]

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(cohort.SAMPLE_COLUMNS)
        yield buffer.getvalue()
        for start in range(0, len(tuples), 2000):
            buffer.seek(0)
            buffer.truncate()
            writer.writerows(tuples[start:start + 2000])
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="samples.csv"'},
    )
