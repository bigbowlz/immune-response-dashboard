from analysis import cohort


def test_build_where_skips_none_and_orders_params():
    where, params = cohort.build_where({"condition": "melanoma", "treatment": None, "time_from_treatment_start": 0})
    assert where == " WHERE subjects.condition = ? AND samples.time_from_treatment_start = ?"
    assert params == ["melanoma", 0]
    assert cohort.build_where({}) == ("", [])


def test_build_where_rejects_unknown_filter():
    import pytest
    with pytest.raises(KeyError):
        cohort.build_where({"colour": "red"})


def test_response_cohort_counts(loaded_conn):
    filters = dict(cohort.RESPONSE_COHORT)
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


def test_filter_options(loaded_conn):
    options = cohort.filter_options(loaded_conn)
    assert options["condition"] == ["carcinoma", "healthy", "melanoma"]
    assert options["treatment"] == ["miraclib", "none", "phauximab"]
    assert options["sample_type"] == ["PBMC", "WB"]
    assert options["time_from_treatment_start"] == [0, 7, 14]


def test_form_answer(loaded_conn):
    assert cohort.form_answer(loaded_conn) == (485, 10206.15)


def test_response_projects(loaded_conn):
    assert cohort.response_projects(loaded_conn) == ["prj1", "prj3"]
