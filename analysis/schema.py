"""Database schema and connection helpers shared by the loader, pipeline and API."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "cell_counts.db"
CSV_PATH = ROOT / "cell-count.csv"

POPULATIONS: tuple[str, ...] = ("b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte")

RAW_TABLES = ("subjects", "samples", "cell_counts")
RESULT_TABLES = ("sample_summary", "response_stats", "cohort_summary", "form_answer", "pipeline_meta")

SCHEMA_SQL = """
CREATE TABLE subjects (
    subject   TEXT PRIMARY KEY,
    project   TEXT NOT NULL,
    condition TEXT NOT NULL,
    age       INTEGER NOT NULL,
    sex       TEXT NOT NULL CHECK (sex IN ('M', 'F')),
    treatment TEXT NOT NULL,
    response  TEXT CHECK (response IN ('yes', 'no'))
);

CREATE TABLE samples (
    sample                    TEXT PRIMARY KEY,
    subject                   TEXT NOT NULL REFERENCES subjects(subject),
    sample_type               TEXT NOT NULL,
    time_from_treatment_start INTEGER NOT NULL
);
CREATE INDEX idx_samples_subject ON samples(subject);

CREATE TABLE cell_counts (
    sample     TEXT NOT NULL REFERENCES samples(sample),
    population TEXT NOT NULL,
    count      INTEGER NOT NULL CHECK (count >= 0),
    PRIMARY KEY (sample, population)
);

-- Result tables. Created empty here, filled by `python -m analysis.pipeline`.
CREATE TABLE sample_summary (
    sample      TEXT NOT NULL REFERENCES samples(sample),
    total_count INTEGER NOT NULL,
    population  TEXT NOT NULL,
    count       INTEGER NOT NULL,
    percentage  REAL NOT NULL,
    PRIMARY KEY (sample, population)
);

CREATE TABLE response_stats (
    project                   TEXT NOT NULL,   -- 'all' for the whole cohort, else a project id (stratified run)
    population                TEXT NOT NULL,
    time_from_treatment_start INTEGER NOT NULL,
    n_responders              INTEGER NOT NULL,
    n_nonresponders           INTEGER NOT NULL,
    median_responders         REAL NOT NULL,
    median_nonresponders      REAL NOT NULL,
    u_statistic               REAL NOT NULL,
    p_raw                     REAL NOT NULL,
    p_adj                     REAL NOT NULL,
    effect_size               REAL NOT NULL,
    significant               INTEGER NOT NULL CHECK (significant IN (0, 1)),
    PRIMARY KEY (project, population, time_from_treatment_start)
);

CREATE TABLE cohort_summary (
    breakdown   TEXT NOT NULL,
    category    TEXT NOT NULL,
    n_samples   INTEGER NOT NULL,
    n_subjects  INTEGER NOT NULL,
    pct_samples REAL NOT NULL,
    PRIMARY KEY (breakdown, category)
);

CREATE TABLE form_answer (
    question    TEXT PRIMARY KEY,
    n_samples   INTEGER NOT NULL,
    mean_b_cell REAL NOT NULL
);

-- Provenance of the last pipeline run: generated_at, csv_sha256, csv_rows, python_version, pandas_version, scipy_version.
CREATE TABLE pipeline_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def resolve_db_path(path: str | os.PathLike | None = None) -> Path:
    """Explicit argument, then the CELL_COUNTS_DB environment variable, then the repo root default."""
    if path is not None:
        return Path(path)
    env = os.environ.get("CELL_COUNTS_DB")
    return Path(env) if env else DEFAULT_DB_PATH


def resolve_csv_path() -> Path:
    """The CELL_COUNTS_CSV environment variable, else cell-count.csv in the repo root."""
    env = os.environ.get("CELL_COUNTS_CSV")
    return Path(env) if env else CSV_PATH


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_db_path(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Drop every table and recreate it, so the loader is idempotent."""
    with conn:
        for table in RESULT_TABLES + tuple(reversed(RAW_TABLES)):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA_SQL)
