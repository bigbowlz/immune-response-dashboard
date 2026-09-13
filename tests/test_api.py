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
    assert body["tables"]["response_stats"] == 45
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


def test_response_stats(client):
    body = client.get("/api/response/stats").json()
    assert body["alpha"] == 0.05 and body["n_tests"] == 15 and body["project"] == "all"
    assert body["projects"] == ["prj1", "prj3"]
    assert len(body["rows"]) == 15 and all(r["project"] == "all" for r in body["rows"])
    assert set(body["rows"][0]) >= {"project", "population", "time_from_treatment_start", "n_responders", "p_raw", "p_adj", "effect_size", "significant"}
    prj3 = client.get("/api/response/stats", params={"project": "prj3"}).json()
    assert len(prj3["rows"]) == 15 and all(r["n_responders"] == 136 and r["n_nonresponders"] == 136 for r in prj3["rows"])
    assert client.get("/api/response/stats", params={"project": "prj2"}).status_code == 422  # not in the cohort
    assert client.get("/api/response/stats", params={"project": "x' OR 1=1"}).status_code == 422


def test_response_samples(client):
    body = client.get("/api/response/samples").json()
    assert len(body["points"]) == 1968 * 5
    p = body["points"][0]
    assert set(p) == {"sample", "subject", "project", "population", "time_from_treatment_start", "response", "percentage"}
    assert {x["response"] for x in body["points"]} == {"yes", "no"}
    prj1 = client.get("/api/response/samples", params={"project": "prj1"}).json()["points"]
    assert len(prj1) == 1152 * 5 and {x["project"] for x in prj1} == {"prj1"}
    assert client.get("/api/response/samples", params={"project": "all"}).json()["points"] == body["points"]


BASELINE_PARAMS = {"condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC", "time_from_treatment_start": "0"}


def test_subsets_omitted_filters_mean_unfiltered(client):
    body = client.get("/api/subsets").json()
    assert body["filters"] == {"condition": None, "treatment": None, "sample_type": None, "time_from_treatment_start": None}
    assert (body["n_samples"], body["n_subjects"]) == (10500, 3500)


def test_subsets_baseline_cohort(client):
    body = client.get("/api/subsets", params=BASELINE_PARAMS).json()
    assert body["filters"] == {"condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC", "time_from_treatment_start": 0}
    assert (body["n_samples"], body["n_subjects"]) == (656, 656)
    project = {r["category"]: r["n_samples"] for r in body["breakdowns"]["project"]}
    assert project == {"prj1": 384, "prj3": 272}
    response = {r["category"]: r["n_subjects"] for r in body["breakdowns"]["response"]}
    assert response == {"yes": 331, "no": 325}
    sex = {r["category"]: r["n_subjects"] for r in body["breakdowns"]["sex"]}
    assert sex == {"M": 344, "F": 312}


def test_subsets_all_relaxes_a_filter(client):
    body = client.get("/api/subsets", params={**BASELINE_PARAMS, "time_from_treatment_start": "all"}).json()
    assert body["filters"]["time_from_treatment_start"] is None
    assert body["n_samples"] == 1968 and body["n_subjects"] == 656
    days = {r["category"]: r["n_samples"] for r in body["breakdowns"]["time_from_treatment_start"]}
    assert days == {0: 656, 7: 656, 14: 656}


def test_subsets_empty_result_is_well_formed(client):
    body = client.get("/api/subsets", params={"condition": "healthy", "treatment": "miraclib"}).json()
    assert body["n_samples"] == 0 and body["n_subjects"] == 0
    assert all(rows == [] for rows in body["breakdowns"].values())


def test_subsets_rejects_unknown_value(client):
    assert client.get("/api/subsets", params={"condition": "unicorn"}).status_code == 422
    assert client.get("/api/subsets", params={"time_from_treatment_start": "abc"}).status_code == 422


def test_subset_options(client):
    body = client.get("/api/subsets/options").json()
    assert body["condition"] == ["carcinoma", "healthy", "melanoma"]
    assert body["time_from_treatment_start"] == [0, 7, 14]


def test_form_answer(client):
    body = client.get("/api/form-answer").json()
    assert (body["n_samples"], body["mean_b_cell"]) == (485, 10206.15)


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
