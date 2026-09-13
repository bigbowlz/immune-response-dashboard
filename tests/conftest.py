from pathlib import Path

import pytest

from analysis import schema
from analysis.loader import load_csv

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "cell-count.csv"


@pytest.fixture(scope="session")
def loaded_db_path(tmp_path_factory) -> Path:
    """A database with the raw tables loaded and the result tables empty."""
    path = tmp_path_factory.mktemp("db") / "loaded.db"
    conn = schema.connect(path)
    schema.create_schema(conn)
    load_csv(CSV, conn)
    conn.close()
    return path


@pytest.fixture()
def loaded_conn(loaded_db_path):
    conn = schema.connect(loaded_db_path)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pipeline_db_path(tmp_path_factory) -> Path:
    """A database with the raw tables loaded and every result table written by the pipeline."""
    from analysis import pipeline

    path = tmp_path_factory.mktemp("db") / "pipeline.db"
    conn = schema.connect(path)
    schema.create_schema(conn)
    load_csv(CSV, conn)
    conn.close()
    pipeline.run(path)
    return path


@pytest.fixture()
def pipeline_conn(pipeline_db_path):
    conn = schema.connect(pipeline_db_path)
    yield conn
    conn.close()
