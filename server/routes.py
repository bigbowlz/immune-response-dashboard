"""API routes. Every endpoint reads tables the pipeline wrote; nothing is computed here beyond SQL."""
from __future__ import annotations

import csv
import io
import sqlite3
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


@router.get("/health")
def health(conn: Conn) -> dict:
    """Row counts per table plus the provenance written by the last pipeline run.

    response_stats holds one stratum for the whole cohort ('all') plus one per project, so a plain
    COUNT(*) would mix strata together; report the 'all' stratum's row count, matching the n_tests a
    caller sees from /api/response/stats?project=all.
    """
    tables = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in RAW_TABLES + RESULT_TABLES if t != "response_stats"}
    tables["response_stats"] = conn.execute("SELECT COUNT(*) FROM response_stats WHERE project = 'all'").fetchone()[0]
    meta = dict(conn.execute("SELECT key, value FROM pipeline_meta").fetchall())
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


def _parse_project(conn: sqlite3.Connection, project: str) -> tuple[str | None, list[str]]:
    """Returns (project filter or None for the whole cohort, list of projects in the cohort)."""
    projects = cohort.response_projects(conn)
    if project == "all":
        return None, projects
    if project not in projects:
        raise HTTPException(status_code=422, detail=f"project must be 'all' or one of {projects}")
    return project, projects


@router.get("/response/stats")
def response_stats(conn: Conn, project: str = "all") -> dict:
    """Part 3 statistics for one stratum: the whole cohort ('all') or a single project."""
    _, projects = _parse_project(conn, project)
    rows = conn.execute(
        f"SELECT * FROM response_stats WHERE project = ? ORDER BY time_from_treatment_start, {POPULATION_ORDER}",
        [project],
    ).fetchall()
    return {"rows": [dict(r) for r in rows], "alpha": ALPHA, "n_tests": len(rows), "project": project, "projects": projects, "cohort": cohort.RESPONSE_COHORT}


@router.get("/response/samples")
def response_samples(conn: Conn, project: str = "all") -> dict:
    """Per-sample percentages behind the Part 3 boxplots, for the whole cohort or one project."""
    project_filter, _ = _parse_project(conn, project)
    return {"points": [dict(r) for r in cohort.response_cohort_points(conn, project_filter)]}


@router.get("/subsets/options")
def subset_options(conn: Conn) -> dict:
    return cohort.filter_options(conn)


def _parse_filter(name: str, raw: str | None, options: dict[str, list]) -> object:
    """Omitted or 'all' means unfiltered; anything else must be a value that exists in the data."""
    if raw is None or raw == "all":
        return None
    allowed = options[name]
    if name == "time_from_treatment_start":
        try:
            value: object = int(raw)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{name} must be an integer or 'all'") from None
    else:
        value = raw
    if value not in allowed:
        raise HTTPException(status_code=422, detail=f"{name} must be one of {allowed} or 'all'")
    return value


@router.get("/subsets")
def subsets(
    conn: Conn,
    condition: str | None = None,
    treatment: str | None = None,
    sample_type: str | None = None,
    time_from_treatment_start: str | None = None,
) -> dict:
    """Part 4: sample and subject counts by project, response, sex and timepoint for any filter combination.

    Each parameter is optional; omitted or 'all' means unfiltered. The baseline cohort the assignment
    asks for is condition=melanoma&treatment=miraclib&sample_type=PBMC&time_from_treatment_start=0.
    """
    options = cohort.filter_options(conn)
    raw = {"condition": condition, "treatment": treatment, "sample_type": sample_type,
           "time_from_treatment_start": time_from_treatment_start}
    filters = {name: _parse_filter(name, raw[name], options) for name in cohort.FILTER_COLUMNS}
    counts = cohort.count_cohort(conn, filters)
    breakdowns = {by: cohort.breakdown(conn, filters, by) for by in cohort.BREAKDOWN_COLUMNS}
    return {"filters": filters, **counts, "breakdowns": breakdowns}


@router.get("/form-answer")
def form_answer(conn: Conn) -> dict:
    row = conn.execute("SELECT question, n_samples, mean_b_cell FROM form_answer").fetchone()
    if row is None:
        raise HTTPException(status_code=503, detail="form_answer is empty. Run `make pipeline` first.")
    return dict(row)
