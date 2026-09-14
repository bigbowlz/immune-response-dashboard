import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from analysis import schema
from analysis.loader import load_csv

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "cell-count.csv"


@pytest.fixture()
def loaded(tmp_path):
    conn = schema.connect(tmp_path / "t.db")
    schema.create_schema(conn)
    report = load_csv(CSV, conn)
    yield conn, report
    conn.close()


def test_report_counts(loaded):
    _, report = loaded
    assert (report.rows, report.samples, report.subjects) == (10500, 10500, 3500)


def test_tables_and_row_counts(loaded):
    conn, _ = loaded
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("subjects", "samples", "cell_counts")}
    assert counts == {"subjects": 3500, "samples": 10500, "cell_counts": 52500}


def test_every_subject_has_three_samples_at_days_0_7_14(loaded):
    conn, _ = loaded
    rows = conn.execute(
        "SELECT subject, COUNT(*) AS n, GROUP_CONCAT(time_from_treatment_start) AS days "
        "FROM samples GROUP BY subject"
    ).fetchall()
    assert all(r["n"] == 3 for r in rows)
    assert all(sorted(int(d) for d in r["days"].split(",")) == [0, 7, 14] for r in rows)


def test_no_missing_counts_and_blank_response_is_null(loaded):
    conn, _ = loaded
    assert conn.execute("SELECT COUNT(*) FROM cell_counts WHERE count IS NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM subjects WHERE response IS NULL").fetchone()[0] == 474
    assert conn.execute("SELECT COUNT(*) FROM subjects WHERE response = ''").fetchone()[0] == 0


def test_result_tables_exist_but_are_empty(loaded):
    conn, _ = loaded
    for t in ("sample_summary", "response_stats", "cohort_summary", "pipeline_meta"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_load_data_script_fails_loudly_when_csv_is_missing(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "load_data.py")],
        cwd=ROOT, env={"PATH": "", "CELL_COUNTS_DB": str(tmp_path / "x.db"), "CELL_COUNTS_CSV": str(tmp_path / "missing.csv")},
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "missing.csv" in result.stderr and "cell-count.csv" in result.stderr


def test_load_data_script_rejects_arguments(tmp_path):
    env = {"PATH": "", "CELL_COUNTS_DB": str(tmp_path / "x.db")}
    bad = subprocess.run([sys.executable, str(ROOT / "load_data.py"), "--db", "x"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert bad.returncode == 2 and "Usage" in bad.stderr
    assert not (tmp_path / "x.db").exists()
    helped = subprocess.run([sys.executable, str(ROOT / "load_data.py"), "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert helped.returncode == 0 and "CELL_COUNTS_DB" in helped.stdout


def test_loader_rejects_inconsistent_subject_metadata(tmp_path):
    bad = tmp_path / "bad.csv"
    header = "project,subject,condition,age,sex,treatment,response,sample,sample_type,time_from_treatment_start,b_cell,cd8_t_cell,cd4_t_cell,nk_cell,monocyte\n"
    bad.write_text(header
                   + "prj1,sbj0,melanoma,50,M,miraclib,yes,s0,PBMC,0,1,2,3,4,5\n"
                   + "prj1,sbj0,melanoma,51,M,miraclib,yes,s1,PBMC,7,1,2,3,4,5\n")
    conn = schema.connect(tmp_path / "t.db")
    schema.create_schema(conn)
    with pytest.raises(ValueError, match="sbj0"):
        load_csv(bad, conn)


def test_loader_rejects_duplicate_sample_id(tmp_path):
    bad = tmp_path / "bad.csv"
    header = "project,subject,condition,age,sex,treatment,response,sample,sample_type,time_from_treatment_start,b_cell,cd8_t_cell,cd4_t_cell,nk_cell,monocyte\n"
    bad.write_text(header
                   + "prj1,sbj0,melanoma,50,M,miraclib,yes,s0,PBMC,0,1,2,3,4,5\n"
                   + "prj1,sbj1,melanoma,51,F,miraclib,no,s0,PBMC,7,1,2,3,4,5\n")
    conn = schema.connect(tmp_path / "t.db")
    schema.create_schema(conn)
    with pytest.raises(ValueError, match="s0"):
        load_csv(bad, conn)


def test_loader_rejects_invalid_sex(tmp_path):
    bad = tmp_path / "bad.csv"
    header = "project,subject,condition,age,sex,treatment,response,sample,sample_type,time_from_treatment_start,b_cell,cd8_t_cell,cd4_t_cell,nk_cell,monocyte\n"
    bad.write_text(header + "prj1,sbj0,melanoma,50,X,miraclib,yes,s0,PBMC,0,1,2,3,4,5\n")
    conn = schema.connect(tmp_path / "t.db")
    schema.create_schema(conn)
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        load_csv(bad, conn)


def test_loader_rejects_non_numeric_count(tmp_path):
    bad = tmp_path / "bad.csv"
    header = "project,subject,condition,age,sex,treatment,response,sample,sample_type,time_from_treatment_start,b_cell,cd8_t_cell,cd4_t_cell,nk_cell,monocyte\n"
    bad.write_text(header + "prj1,sbj0,melanoma,50,M,miraclib,yes,s0,PBMC,0,1,x,3,4,5\n")
    conn = schema.connect(tmp_path / "t.db")
    schema.create_schema(conn)
    with pytest.raises(ValueError, match="cd8_t_cell"):
        load_csv(bad, conn)


def test_load_data_script_creates_db_at_env_path(tmp_path):
    db = tmp_path / "script.db"
    result = subprocess.run(
        [sys.executable, str(ROOT / "load_data.py")],
        cwd=ROOT, env={"PATH": "", "CELL_COUNTS_DB": str(db)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert db.exists()
    assert "10500" in result.stdout
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 10500


def test_create_schema_drops_tables_from_older_schemas(tmp_path):
    conn = schema.connect(tmp_path / "old.db")
    conn.execute("CREATE TABLE leftover (x INTEGER)")
    conn.commit()
    schema.create_schema(conn)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert "leftover" not in names
    assert set(schema.RAW_TABLES + schema.RESULT_TABLES) <= names
