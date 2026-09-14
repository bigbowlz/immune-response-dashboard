"""Integration test: the pipeline reproduces the verification numbers from the working checklist."""
import subprocess
import sys
from pathlib import Path

import pytest
from scipy import stats as sps

from analysis.schema import POPULATIONS

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_KEY = ("melanoma", "miraclib", "PBMC", "all")
HEALTHY_KEY = ("healthy", "none", "all", "all")
EMPTY_KEY = ("carcinoma", "miraclib", "PBMC", "prj2")
ALL_KEY = ("all", "all", "all", "all")

_KEY_WHERE = "condition = ? AND treatment = ? AND sample_type = ? AND project = ? AND timepoints = ?"


def q(conn, sql, *params):
    return conn.execute(sql, params).fetchall()


def stats_rows(conn, key, family):
    return q(
        conn,
        f"SELECT * FROM response_stats WHERE {_KEY_WHERE} ORDER BY population, time_from_treatment_start",
        *key, family,
    )


def strata_row(conn, key, family):
    rows = q(conn, f"SELECT * FROM response_strata WHERE {_KEY_WHERE}", *key, family)
    assert len(rows) == 1
    return rows[0]


def test_raw_table_counts(pipeline_conn):
    assert q(pipeline_conn, "SELECT COUNT(*) FROM samples")[0][0] == 10500
    assert q(pipeline_conn, "SELECT COUNT(DISTINCT sample) FROM samples")[0][0] == 10500
    assert q(pipeline_conn, "SELECT COUNT(*) FROM subjects")[0][0] == 3500
    assert tuple(q(pipeline_conn, "SELECT MIN(n), MAX(n) FROM (SELECT COUNT(*) AS n FROM samples GROUP BY subject)")[0]) == (3, 3)


def test_sample_summary_has_required_columns_and_sums_to_100(pipeline_conn):
    cols = [r[1] for r in q(pipeline_conn, "PRAGMA table_info(sample_summary)")]
    assert cols == ["sample", "total_count", "population", "count", "percentage"]
    assert q(pipeline_conn, "SELECT COUNT(*) FROM sample_summary")[0][0] == 52500
    worst = q(pipeline_conn, "SELECT MAX(ABS(s - 100)) FROM (SELECT SUM(percentage) AS s FROM sample_summary GROUP BY sample)")[0][0]
    assert worst < 1e-9
    row = q(pipeline_conn, "SELECT total_count, count, percentage FROM sample_summary WHERE sample = 'sample00000' AND population = 'b_cell'")[0]
    assert tuple(row) == (10908 + 24440 + 20491 + 13864 + 23511, 10908, pytest.approx(10908 / 93214 * 100))


def test_response_stats_and_strata_table_counts(pipeline_conn):
    """192 cohort keys x (15 all-family cells + 3 x 5 day-family cells) and x 4 families."""
    assert q(pipeline_conn, "SELECT COUNT(*) FROM response_stats")[0][0] == 5760
    assert q(pipeline_conn, "SELECT COUNT(*) FROM response_strata")[0][0] == 768


def test_default_cohort_family_all(pipeline_conn):
    rows = stats_rows(pipeline_conn, DEFAULT_KEY, "all")
    assert len(rows) == 15
    ok = [r for r in rows if r["status"] == "ok"]
    assert len(ok) == 15
    best = min(ok, key=lambda r: r["p_adj"])
    assert (best["population"], best["time_from_treatment_start"]) == ("b_cell", 14)
    assert 0.2 < best["p_adj"] < 0.25
    assert all(r["significant"] == 0 for r in rows)
    strata = strata_row(pipeline_conn, DEFAULT_KEY, "all")
    assert strata["n_tests"] == 15


def test_default_cohort_family_14_matches_scipy_bh_over_the_days_raw_p(pipeline_conn):
    day_all = {r["population"]: r for r in stats_rows(pipeline_conn, DEFAULT_KEY, "all") if r["time_from_treatment_start"] == 14}
    raw_ps = [day_all[p]["p_raw"] for p in POPULATIONS]
    expected = sps.false_discovery_control(raw_ps, method="bh")

    day14 = {r["population"]: r for r in stats_rows(pipeline_conn, DEFAULT_KEY, "14")}
    assert len(day14) == 5
    strata = strata_row(pipeline_conn, DEFAULT_KEY, "14")
    assert strata["n_tests"] == 5
    for population, exp in zip(POPULATIONS, expected):
        assert day14[population]["p_adj"] == pytest.approx(exp, abs=1e-9)
    assert 0.06 < day14["b_cell"]["p_adj"] < 0.08


def test_healthy_cohort_has_no_recorded_responses(pipeline_conn):
    rows = stats_rows(pipeline_conn, HEALTHY_KEY, "all")
    assert len(rows) == 15
    assert all(r["status"] == "unavailable" for r in rows)
    assert all(r["reason"] == "no recorded responses in this cohort" for r in rows)
    strata = strata_row(pipeline_conn, HEALTHY_KEY, "all")
    assert strata["n_tests"] == 0
    assert strata["n_samples"] == strata["n_missing_response"] == 1422


def test_cohort_with_no_matching_samples(pipeline_conn):
    rows = stats_rows(pipeline_conn, EMPTY_KEY, "all")
    assert len(rows) == 15
    assert all(r["status"] == "unavailable" for r in rows)
    assert all(r["reason"] == "no samples match this cohort at this timepoint" for r in rows)
    strata = strata_row(pipeline_conn, EMPTY_KEY, "all")
    assert strata["n_samples"] == 0


def test_unfiltered_cohort_family_all(pipeline_conn):
    strata = strata_row(pipeline_conn, ALL_KEY, "all")
    assert strata["n_samples"] == 10500
    assert strata["n_subjects"] == 3500
    assert strata["n_missing_response"] == 1422
    assert strata["n_tests"] == 15


def test_cohort_summary_matches_verification_numbers(pipeline_conn):
    rows = q(pipeline_conn, "SELECT breakdown, category, n_samples, n_subjects FROM cohort_summary")
    table = {(r["breakdown"], r["category"]): (r["n_samples"], r["n_subjects"]) for r in rows}
    assert table[("total", "all")] == (656, 656)
    assert table[("project", "prj1")] == (384, 384)
    assert table[("project", "prj3")] == (272, 272)
    assert table[("response", "yes")] == (331, 331)
    assert table[("response", "no")] == (325, 325)
    assert table[("sex", "M")] == (344, 344)
    assert table[("sex", "F")] == (312, 312)


def test_pipeline_is_idempotent(loaded_db_path, tmp_path):
    """Runs on its own copy so the session-scoped pipeline DB that test_api reads is never rewritten mid-session."""
    import shutil
    from dataclasses import replace

    from analysis import pipeline

    own = tmp_path / "own.db"
    shutil.copy(loaded_db_path, own)
    first = pipeline.run(own)
    second = pipeline.run(own)
    assert replace(first, generated_at="") == replace(second, generated_at="")
    assert first.summary_rows == 52500 and first.stats_rows == 5760 and first.strata == 768


def test_pipeline_meta_records_provenance(pipeline_conn):
    meta = dict(q(pipeline_conn, "SELECT key, value FROM pipeline_meta"))
    assert set(meta) == {"generated_at", "csv_sha256", "csv_rows", "python_version", "pandas_version", "scipy_version"}
    assert len(meta["csv_sha256"]) == 64 and meta["csv_rows"] == "10500"


def test_module_entry_point_prints_report(tmp_path):
    db = tmp_path / "e2e.db"
    env = {"PATH": "", "CELL_COUNTS_DB": str(db)}
    load = subprocess.run([sys.executable, str(ROOT / "load_data.py")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert load.returncode == 0, load.stderr
    run = subprocess.run([sys.executable, "-m", "analysis.pipeline"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "response_stats: 5760 rows over 768 strata; default cohort: 15 tests, smallest adjusted p 0.216" in run.stdout
