"""Integration test: the pipeline reproduces the verification numbers from the working checklist."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def q(conn, sql, *params):
    return conn.execute(sql, params).fetchall()


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


def test_response_stats_cover_five_populations_at_three_timepoints(pipeline_conn):
    rows = q(pipeline_conn, "SELECT * FROM response_stats WHERE project = 'all' ORDER BY population, time_from_treatment_start")
    assert len(rows) == 15
    assert {r["time_from_treatment_start"] for r in rows} == {0, 7, 14}
    assert all(r["n_responders"] + r["n_nonresponders"] == 656 for r in rows)
    assert all(r["n_responders"] == 331 and r["n_nonresponders"] == 325 for r in rows)
    assert all(0 <= r["p_raw"] <= 1 and r["p_raw"] <= r["p_adj"] <= 1 for r in rows)
    assert all(-1 <= r["effect_size"] <= 1 for r in rows)
    assert all(r["significant"] == int(r["p_adj"] < 0.05) for r in rows)


def test_response_stats_are_stratified_by_project(pipeline_conn):
    assert q(pipeline_conn, "SELECT COUNT(*) FROM response_stats")[0][0] == 45
    strata = {r[0]: r[1] for r in q(pipeline_conn, "SELECT project, COUNT(*) FROM response_stats GROUP BY project")}
    assert strata == {"all": 15, "prj1": 15, "prj3": 15}
    prj1 = q(pipeline_conn, "SELECT DISTINCT n_responders, n_nonresponders FROM response_stats WHERE project = 'prj1'")
    prj3 = q(pipeline_conn, "SELECT DISTINCT n_responders, n_nonresponders FROM response_stats WHERE project = 'prj3'")
    assert [tuple(r) for r in prj1] == [(195, 189)] and [tuple(r) for r in prj3] == [(136, 136)]
    # BH is applied within each stratum: the largest adjusted p in a stratum equals its largest raw p
    for project in ("all", "prj1", "prj3"):
        top = q(pipeline_conn, "SELECT MAX(p_raw), MAX(p_adj) FROM response_stats WHERE project = ?", project)[0]
        assert top[0] == pytest.approx(top[1])
    # Also null within each project (documentation test, same caveat as below)
    best = q(pipeline_conn, "SELECT project, population, time_from_treatment_start, p_adj FROM response_stats WHERE project != 'all' ORDER BY p_adj LIMIT 1")[0]
    assert (best["project"], best["population"], best["time_from_treatment_start"]) == ("prj1", "b_cell", 14)
    assert 0.35 < best["p_adj"] < 0.45


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
    assert first.summary_rows == 52500 and first.stats_rows == 45


def test_pipeline_meta_records_provenance(pipeline_conn):
    meta = dict(q(pipeline_conn, "SELECT key, value FROM pipeline_meta"))
    assert set(meta) == {"generated_at", "csv_sha256", "csv_rows", "python_version", "pandas_version", "scipy_version"}
    assert len(meta["csv_sha256"]) == 64 and meta["csv_rows"] == "10500"


def test_no_population_is_significant_on_this_dataset(pipeline_conn):
    """Documents the real result: after BH correction no per-timepoint test reaches 0.05.
    The smallest adjusted p is b_cell at day 14 (0.2162 with scipy 1.18.1). This is a documentation test:
    if it fails after a data or scipy change, re-read the README story before touching the assertion."""
    rows = q(pipeline_conn, "SELECT population, time_from_treatment_start, p_adj FROM response_stats WHERE project = 'all' ORDER BY p_adj LIMIT 1")
    assert (rows[0]["population"], rows[0]["time_from_treatment_start"]) == ("b_cell", 14)
    assert 0.2 < rows[0]["p_adj"] < 0.25
    assert q(pipeline_conn, "SELECT COUNT(*) FROM response_stats WHERE significant = 1")[0][0] == 0  # in every stratum


def test_module_entry_point_prints_report(tmp_path):
    db = tmp_path / "e2e.db"
    env = {"PATH": "", "CELL_COUNTS_DB": str(db)}
    load = subprocess.run([sys.executable, str(ROOT / "load_data.py")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert load.returncode == 0, load.stderr
    run = subprocess.run([sys.executable, "-m", "analysis.pipeline"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "response_stats: 45 tests" in run.stdout
    assert "no population reaches adjusted p" in run.stdout
