import pytest

from analysis import cohort


def test_build_where_skips_none_and_orders_params():
    where, params = cohort.build_where({"condition": "melanoma", "treatment": None, "time_from_treatment_start": 0})
    assert where == " WHERE subjects.condition = ? AND samples.time_from_treatment_start = ?"
    assert params == ["melanoma", 0]
    assert cohort.build_where({}) == ("", [])


def test_build_where_rejects_unknown_filter():
    with pytest.raises(KeyError):
        cohort.build_where({"colour": "red"})


def test_default_cohort_counts(loaded_conn):
    filters = dict(cohort.DEFAULT_COHORT)
    assert cohort.count_cohort(loaded_conn, filters) == {"n_samples": 1968, "n_subjects": 656}
    by_response = {r["category"]: r for r in cohort.breakdown(loaded_conn, filters, "response")}
    assert by_response["yes"]["n_samples"] == 993
    assert by_response["no"]["n_samples"] == 975


def test_baseline_cohort_breakdowns(loaded_conn):
    filters = dict(cohort.BASELINE_COHORT)
    assert cohort.count_cohort(loaded_conn, filters) == {"n_samples": 656, "n_subjects": 656}
    project = {r["category"]: r["n_samples"] for r in cohort.breakdown(loaded_conn, filters, "project")}
    assert project == {"prj1": 384, "prj3": 272}
    response = {r["category"]: r["n_subjects"] for r in cohort.breakdown(loaded_conn, filters, "response")}
    assert response == {"yes": 331, "no": 325}
    sex = {r["category"]: r["n_subjects"] for r in cohort.breakdown(loaded_conn, filters, "sex")}
    assert sex == {"M": 344, "F": 312}
    pct = {r["category"]: r["pct_samples"] for r in cohort.breakdown(loaded_conn, filters, "project")}
    assert pct == {"prj1": round(384 / 656 * 100, 2), "prj3": round(272 / 656 * 100, 2)}


def test_breakdown_reports_null_response_as_unknown(loaded_conn):
    rows = cohort.breakdown(loaded_conn, {"condition": "healthy"}, "response")
    assert [r["category"] for r in rows] == ["unknown"]
    assert rows[0]["n_samples"] == 1422


def test_breakdown_orders_null_category_last(loaded_conn):
    rows = cohort.breakdown(loaded_conn, {}, "response")
    assert [r["category"] for r in rows] == ["no", "yes", "unknown"]


def test_cohort_options(loaded_conn):
    options = cohort.cohort_options(loaded_conn)
    assert list(options.keys()) == list(cohort.FILTER_COLUMNS.keys())
    assert options["condition"] == ["carcinoma", "healthy", "melanoma"]
    assert options["treatment"] == ["miraclib", "none", "phauximab"]
    assert options["sample_type"] == ["PBMC", "WB"]
    assert options["project"] == ["prj1", "prj2", "prj3"]
    assert options["time_from_treatment_start"] == [0, 7, 14]
    assert all(isinstance(v, int) for v in options["time_from_treatment_start"])


def test_response_points_runs_and_returns_list(loaded_conn):
    # sample_summary is empty on loaded_conn (Task 2 populates it); the query must still run.
    points = cohort.response_points(loaded_conn, {"condition": "melanoma", "treatment": "miraclib", "sample_type": "PBMC"})
    assert points == []


def test_count_samples(loaded_conn):
    assert cohort.count_samples(loaded_conn, {}) == 10500
    assert cohort.count_samples(loaded_conn, {"condition": "healthy", "treatment": "miraclib"}) == 0


def test_missing_response_count(loaded_conn):
    assert cohort.missing_response_count(loaded_conn, {}) == 1422
    assert cohort.missing_response_count(loaded_conn, {"condition": "melanoma"}) == 0


def test_list_samples_default_page_sorted_by_sample(loaded_conn):
    rows = cohort.list_samples(loaded_conn, {})
    assert len(rows) == 50
    assert rows[0]["sample"] == "sample00000"
    assert list(rows[0].keys()) == list(cohort.SAMPLE_COLUMNS)
    assert [r["sample"] for r in rows] == sorted(r["sample"] for r in rows)


def test_list_samples_sort_response_desc_puts_yes_first_none_last(loaded_conn):
    rows = cohort.list_samples(loaded_conn, {}, sort="response", direction="desc", limit=10500)
    responses = [r["response"] for r in rows]
    assert responses[0] == "yes"
    assert responses[-1] is None
    first_no_index = responses.index("no")
    first_none_index = responses.index(None)
    assert first_no_index < first_none_index


def test_list_samples_limit_and_offset(loaded_conn):
    rows = cohort.list_samples(loaded_conn, {}, limit=5, offset=2)
    assert len(rows) == 5
    full = cohort.list_samples(loaded_conn, {}, limit=10)
    assert [r["sample"] for r in rows] == [r["sample"] for r in full[2:7]]


def test_list_samples_rejects_invalid_sort_or_direction(loaded_conn):
    with pytest.raises(ValueError):
        cohort.list_samples(loaded_conn, {}, sort="not_a_column")
    with pytest.raises(ValueError):
        cohort.list_samples(loaded_conn, {}, direction="sideways")


def test_list_samples_total_matches_count_cohort(loaded_conn):
    filters = dict(cohort.BASELINE_COHORT)
    total = cohort.count_samples(loaded_conn, filters)
    assert total == 656
    assert total == cohort.count_cohort(loaded_conn, filters)["n_samples"]
    rows = cohort.list_samples(loaded_conn, filters, limit=1000)
    assert len(rows) == 656
