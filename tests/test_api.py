import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(pipeline_db_path, monkeypatch):
    monkeypatch.setenv("CELL_COUNTS_DB", str(pipeline_db_path))
    monkeypatch.setenv("SERVE_FRONTEND", "0")
    from server.app import app
    return TestClient(app)


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["tables"]["samples"] == 10500
    assert body["tables"]["response_stats"] == 5760
    assert body["db_path"] == "pipeline.db"  # file name only; never the server's absolute path
    assert set(body["meta"]) >= {"generated_at", "csv_sha256"}


def test_frequencies_default_page(client):
    body = client.get("/api/frequencies").json()
    assert body["total"] == 52500
    assert (body["limit"], body["offset"], len(body["rows"])) == (50, 0, 50)
    assert list(body["rows"][0].keys()) == ["sample", "total_count", "population", "count", "percentage"]
    assert body["rows"][0]["sample"] == "sample00000" and body["rows"][0]["population"] == "b_cell"
    assert [r["population"] for r in body["rows"][:5]] == ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]


def test_frequencies_search_sort_and_paging(client):
    filtered = client.get("/api/frequencies", params={"search": "sample00000"}).json()
    assert filtered["total"] == 5
    assert {r["population"] for r in filtered["rows"]} == {"b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"}
    page = client.get("/api/frequencies", params={"limit": 5, "offset": 5}).json()
    assert page["total"] == 52500 and len(page["rows"]) == 5 and page["rows"][0]["sample"] == "sample00001"
    top = client.get("/api/frequencies", params={"sort": "percentage", "dir": "desc", "limit": 1}).json()
    assert top["rows"][0]["percentage"] == pytest.approx(
        client.get("/api/frequencies", params={"sort": "percentage", "dir": "desc", "limit": 1, "offset": 0}).json()["rows"][0]["percentage"]
    )
    assert top["rows"][0]["percentage"] >= 40  # the largest single-population share in the file
    assert client.get("/api/frequencies", params={"sort": "DROP TABLE"}).status_code == 422
    assert client.get("/api/frequencies", params={"limit": 0}).status_code == 422
    assert client.get("/api/frequencies", params={"limit": 501}).status_code == 422
    assert client.get("/api/frequencies", params={"search": "x" * 101}).status_code == 422
    assert client.get("/api/frequencies", params={"search": "nothing-matches"}).json() == {"rows": [], "total": 0, "limit": 50, "offset": 0}
    # LIKE wildcards are literal characters in a search
    assert client.get("/api/frequencies", params={"search": "%"}).json()["total"] == 0
    assert client.get("/api/frequencies", params={"search": "cd8_t"}).json()["total"] == 10500
    assert client.get("/api/frequencies", params={"search": "cd8xt"}).json()["total"] == 0
    # sort=population uses the fixed population order, not alphabetical
    by_pop = client.get("/api/frequencies", params={"sort": "population", "dir": "asc", "limit": 3}).json()["rows"]
    assert [r["population"] for r in by_pop] == ["b_cell"] * 3 and [r["sample"] for r in by_pop] == ["sample00000", "sample00001", "sample00002"]
    last = client.get("/api/frequencies", params={"sort": "population", "dir": "desc", "limit": 1}).json()["rows"][0]
    assert last["population"] == "monocyte"


def test_frequencies_csv(client):
    response = client.get("/api/frequencies.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "sample,total_count,population,count,percentage"
    assert len(lines) == 52501
    sorted_csv = client.get("/api/frequencies.csv", params={"search": "sample00000", "sort": "count", "dir": "desc"}).text.strip().splitlines()
    counts = [int(line.split(",")[3]) for line in sorted_csv[1:]]
    assert counts == sorted(counts, reverse=True) and len(counts) == 5


def test_cohort_options(client):
    body = client.get("/api/cohort/options").json()
    assert body["condition"] == ["carcinoma", "healthy", "melanoma"]
    assert body["treatment"] == ["miraclib", "none", "phauximab"]
    assert body["sample_type"] == ["PBMC", "WB"]
    assert body["project"] == ["prj1", "prj2", "prj3"]
    assert body["time_from_treatment_start"] == [0, 7, 14]


def test_cohort_summary_default(client):
    body = client.get("/api/cohort/summary").json()
    assert body["filters"] == {
        "condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC",
        "project": "all", "time_from_treatment_start": "all",
    }
    assert (body["n_samples"], body["n_subjects"], body["n_missing_response"]) == (1968, 656, 0)
    response = {r["category"]: r["n_samples"] for r in body["breakdowns"]["response"]}
    assert response == {"yes": 993, "no": 975}
    assert set(body["breakdowns"]) == {"project", "response", "sex", "time_from_treatment_start"}


def test_cohort_summary_all_relaxed_has_unknown_response(client):
    params = {"condition": "all", "treatment": "all", "sample_type": "all", "project": "all", "time_from_treatment_start": "all"}
    body = client.get("/api/cohort/summary", params=params).json()
    assert body["n_samples"] == 10500
    response = {r["category"]: r["n_samples"] for r in body["breakdowns"]["response"]}
    assert response["unknown"] == 1422


def test_cohort_stats_default(client):
    body = client.get("/api/cohort/stats").json()
    assert body["filters"]["project"] == "all" and body["family"] == "all"
    assert body["alpha"] == 0.05
    assert body["n_tests"] == 15 and len(body["rows"]) == 15
    assert (body["n_samples"], body["n_subjects"], body["n_missing_response"]) == (1968, 656, 0)
    min_row = min(body["rows"], key=lambda r: r["p_adj"])
    assert min_row["population"] == "b_cell" and min_row["time_from_treatment_start"] == 14
    assert 0.2 <= min_row["p_adj"] <= 0.25
    assert all("status" in r and "reason" in r for r in body["rows"])
    timepoints = [r["time_from_treatment_start"] for r in body["rows"]]
    assert timepoints == sorted(timepoints)


def test_cohort_stats_single_timepoint(client):
    body = client.get("/api/cohort/stats", params={"time_from_treatment_start": "14"}).json()
    assert body["family"] == "14"
    assert body["n_tests"] == 5 and len(body["rows"]) == 5
    assert all(r["time_from_treatment_start"] == 14 for r in body["rows"])


def test_cohort_stats_healthy_none_all_unavailable(client):
    body = client.get("/api/cohort/stats", params={"condition": "healthy", "treatment": "none"}).json()
    assert len(body["rows"]) == 15 and body["n_tests"] == 0
    assert all(r["status"] == "unavailable" for r in body["rows"])
    assert all(r["reason"] == "no recorded responses in this cohort" for r in body["rows"])
    assert all(r["p_adj"] is None for r in body["rows"])


def test_cohort_stats_no_matching_samples(client):
    body = client.get("/api/cohort/stats", params={"project": "prj2"}).json()
    assert all(r["status"] == "unavailable" for r in body["rows"])
    assert all(r["reason"] == "no samples match this cohort at this timepoint" for r in body["rows"])


def test_cohort_points_default(client):
    body = client.get("/api/cohort/points").json()
    assert len(body["points"]) == 1968 * 5
    p = body["points"][0]
    assert set(p) == {"sample", "subject", "project", "population", "time_from_treatment_start", "response", "percentage"}
    assert {x["response"] for x in body["points"]} == {"yes", "no"}


def test_cohort_samples_total_matches_summary(client):
    for params in (
        {},
        {"condition": "healthy", "treatment": "none"},
        {"condition": "all", "treatment": "all", "sample_type": "all", "project": "all", "time_from_treatment_start": "all"},
    ):
        summary = client.get("/api/cohort/summary", params=params).json()
        samples = client.get("/api/cohort/samples", params=params).json()
        assert samples["total"] == summary["n_samples"]
    assert client.get("/api/cohort/samples", params={"condition": "all", "treatment": "all", "sample_type": "all", "project": "all", "time_from_treatment_start": "all"}).json()["total"] == 10500


def test_cohort_samples_paging_and_sort(client):
    body = client.get("/api/cohort/samples", params={"limit": 2}).json()
    assert (body["limit"], body["offset"], len(body["rows"])) == (2, 0, 2)
    assert body["total"] == 1968
    assert set(body["rows"][0]) == {"sample", "subject", "project", "condition", "treatment", "sample_type", "time_from_treatment_start", "response", "sex"}
    page2 = client.get("/api/cohort/samples", params={"limit": 2, "offset": 2}).json()
    assert page2["rows"][0]["sample"] != body["rows"][0]["sample"]
    desc = client.get("/api/cohort/samples", params={"sort": "subject", "dir": "desc", "limit": 1}).json()
    asc = client.get("/api/cohort/samples", params={"sort": "subject", "dir": "asc", "limit": 1}).json()
    assert desc["rows"][0]["subject"] > asc["rows"][0]["subject"]
    assert client.get("/api/cohort/samples", params={"limit": 0}).status_code == 422
    assert client.get("/api/cohort/samples", params={"limit": 501}).status_code == 422
    assert client.get("/api/cohort/samples", params={"offset": -1}).status_code == 422


def test_cohort_samples_csv(client):
    response = client.get("/api/cohort/samples.csv", params={"time_from_treatment_start": "0"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="samples.csv"'
    lines = response.text.strip().splitlines()
    assert lines[0] == "sample,subject,project,condition,treatment,sample_type,time_from_treatment_start,response,sex"
    assert len(lines) == 657


def test_cohort_samples_null_response_serializes_as_empty_csv_and_null_json(client):
    params = {"condition": "healthy", "treatment": "none"}
    json_body = client.get("/api/cohort/samples", params={**params, "limit": 1}).json()
    assert json_body["rows"][0]["response"] is None
    csv_text = client.get("/api/cohort/samples.csv", params=params).text
    first_row = csv_text.strip().splitlines()[1].split(",")
    assert first_row[7] == ""  # response column, per SAMPLE_COLUMNS order


def test_cohort_filters_reject_unknown_values(client):
    assert client.get("/api/cohort/summary", params={"condition": "unicorn"}).status_code == 422
    assert client.get("/api/cohort/summary", params={"project": "prj9"}).status_code == 422
    assert client.get("/api/cohort/summary", params={"time_from_treatment_start": "abc"}).status_code == 422
    assert client.get("/api/cohort/samples", params={"sort": "DROP"}).status_code == 422
    assert client.get("/api/cohort/stats", params={"condition": "x' OR 1=1"}).status_code == 422


def test_removed_endpoints_are_gone(client):
    assert client.get("/api/response/stats").status_code == 404
    assert client.get("/api/response/samples").status_code == 404
    assert client.get("/api/subsets").status_code == 404
    assert client.get("/api/subsets/options").status_code == 404


def test_missing_db_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("CELL_COUNTS_DB", str(tmp_path / "nope.db"))
    monkeypatch.setenv("SERVE_FRONTEND", "0")
    from server.app import app
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert "make pipeline" in response.json()["detail"]


def test_health_before_pipeline_returns_503(loaded_db_path, monkeypatch):
    # Raw tables loaded, result tables empty: the loader ran but `make pipeline` never did.
    monkeypatch.setenv("CELL_COUNTS_DB", str(loaded_db_path))
    monkeypatch.setenv("SERVE_FRONTEND", "0")
    from server.app import app
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert "make pipeline" in response.json()["detail"]


def test_api_process_never_imports_dataframe_libraries():
    code = (
        "import sys, server.app, api.index; "
        "print(sorted({m.split('.')[0] for m in sys.modules} & {'pandas', 'numpy', 'scipy', 'statsmodels'}))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_root_requirements_have_no_dataframe_libraries():
    text = (ROOT / "requirements.txt").read_text().lower()
    assert not any(lib in text for lib in ("pandas", "numpy", "scipy", "statsmodels"))
