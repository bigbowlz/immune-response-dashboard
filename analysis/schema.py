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
RESULT_TABLES = ("sample_summary", "response_stats", "response_strata", "cohort_summary", "pipeline_meta")

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

-- One row per selectable cohort key (condition, treatment, sample_type, project, each 'all' or a
-- value) x correction family (timepoints: 'all', '0', '7', '14') x population x timepoint.
-- Statistics are NULL and status is 'unavailable' when the cell could not be tested; see `reason`.
CREATE TABLE response_stats (
    condition                 TEXT NOT NULL,   -- 'all' or a value
    treatment                 TEXT NOT NULL,   -- 'all' or a value
    sample_type               TEXT NOT NULL,   -- 'all' or a value
    project                   TEXT NOT NULL,   -- 'all' or a value
    timepoints                TEXT NOT NULL,   -- correction family: 'all', '0', '7', '14'
    population                TEXT NOT NULL,
    time_from_treatment_start INTEGER NOT NULL,
    n_responders              INTEGER NOT NULL,
    n_nonresponders           INTEGER NOT NULL,
    median_responders         REAL,
    median_nonresponders      REAL,
    u_statistic               REAL,
    p_raw                     REAL,
    p_adj                     REAL,
    effect_size               REAL,
    significant               INTEGER NOT NULL CHECK (significant IN (0, 1)),
    status                    TEXT NOT NULL CHECK (status IN ('ok', 'unavailable')),
    reason                    TEXT,
    PRIMARY KEY (condition, treatment, sample_type, project, timepoints, population, time_from_treatment_start)
);

-- One row per selectable cohort key x correction family, so the API can read a stratum's
-- sample/subject/missing-response counts and its family size without recomputing them.
CREATE TABLE response_strata (
    condition          TEXT NOT NULL,
    treatment          TEXT NOT NULL,
    sample_type        TEXT NOT NULL,
    project            TEXT NOT NULL,
    timepoints         TEXT NOT NULL,
    n_samples          INTEGER NOT NULL,
    n_subjects         INTEGER NOT NULL,
    n_missing_response INTEGER NOT NULL,
    n_tests            INTEGER NOT NULL,
    PRIMARY KEY (condition, treatment, sample_type, project, timepoints)
);

CREATE TABLE cohort_summary (
    breakdown   TEXT NOT NULL,
    category    TEXT NOT NULL,
    n_samples   INTEGER NOT NULL,
    n_subjects  INTEGER NOT NULL,
    pct_samples REAL NOT NULL,
    PRIMARY KEY (breakdown, category)
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
    """Drop every table and recreate it, so the loader is idempotent.

    Every user table is dropped, not just the ones this version knows about, so a database written
    by an older schema never keeps tables the current pipeline no longer produces.
    """
    with conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        existing = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        for table in existing:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
