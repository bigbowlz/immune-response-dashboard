import math

import pandas as pd
import pytest

from analysis import stats
from analysis.schema import POPULATIONS


def test_sample_summary_percentages_and_columns():
    counts = pd.DataFrame({
        "sample": ["s1"] * 5 + ["s2"] * 5,
        "population": list(POPULATIONS) * 2,
        "count": [10, 20, 30, 40, 0, 1, 1, 1, 1, 1],
    })
    out = stats.compute_sample_summary(counts)
    assert list(out.columns) == ["sample", "total_count", "population", "count", "percentage"]
    s1 = out[out["sample"] == "s1"].set_index("population")
    assert s1["total_count"].unique().tolist() == [100]
    assert s1.loc["b_cell", "percentage"] == 10.0
    assert s1.loc["monocyte", "percentage"] == 0.0
    s2 = out[out["sample"] == "s2"]
    assert s2["percentage"].sum() == pytest.approx(100.0)
    assert len(out) == 10


def test_compare_groups_complete_separation():
    r = stats.compare_groups([5, 6, 7], [1, 2, 3])
    assert (r.n_responders, r.n_nonresponders) == (3, 3)
    assert (r.median_responders, r.median_nonresponders) == (6, 2)
    assert r.u_statistic == 9
    assert r.effect_size == 1.0
    assert r.p_raw == pytest.approx(0.1)  # exact two-sided p for n = 3 vs 3


def test_compare_groups_reversed_sign_and_no_difference():
    assert stats.compare_groups([1, 2, 3], [5, 6, 7]).effect_size == -1.0
    same = stats.compare_groups([1, 2, 3, 4], [1, 2, 3, 4])
    assert same.effect_size == 0.0
    assert same.p_raw == pytest.approx(1.0)


def test_compare_groups_rejects_empty_group():
    with pytest.raises(ValueError, match="empty"):
        stats.compare_groups([], [1, 2, 3])


def test_benjamini_hochberg_known_values():
    assert stats.benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05]) == pytest.approx([0.05] * 5)
    assert stats.benjamini_hochberg([0.001, 0.04, 0.5]) == pytest.approx([0.003, 0.06, 0.5])
    adjusted = stats.benjamini_hochberg([0.5, 0.001, 0.04])
    assert adjusted == pytest.approx([0.5, 0.003, 0.06])  # order preserved


def test_sample_summary_rejects_zero_total():
    counts = pd.DataFrame({"sample": ["s1"] * 5, "population": list(POPULATIONS), "count": [0] * 5})
    with pytest.raises(ValueError, match="s1"):
        stats.compute_sample_summary(counts)


def _points(rows):
    """rows: list of (population, day, subject, response, percentage)"""
    return pd.DataFrame(
        rows,
        columns=["population", "time_from_treatment_start", "subject", "response", "percentage"],
    )


def test_compare_cells_columns_are_population_ordered_and_timepoint_ordered():
    points = _points([])
    out = stats.compare_cells(points, [0])
    assert list(out.columns) == stats.CELL_COLUMNS
    assert out["population"].tolist() == list(POPULATIONS)
    assert (out["time_from_treatment_start"] == 0).all()


def test_compare_cells_empty_frame_is_unavailable_for_every_cell():
    out = stats.compare_cells(_points([]), [0, 7])
    assert len(out) == len(POPULATIONS) * 2
    assert (out["status"] == "unavailable").all()
    assert (out["reason"] == "no samples match this cohort at this timepoint").all()
    assert out["p_raw"].isna().all()


def test_compare_cells_ok_and_missing_group():
    rows = []
    for i in range(4):
        rows.append(("b_cell", 0, f"sbj{i}a", "yes", 10.0 + i))
        rows.append(("b_cell", 0, f"sbj{i}b", "no", 1.0 + i))
    # cd8_t_cell at day 0 has only responders, no non-responders.
    for i in range(3):
        rows.append(("cd8_t_cell", 0, f"sbjc{i}", "yes", 5.0))
    out = stats.compare_cells(_points(rows), [0])

    b_cell = out[out["population"] == "b_cell"].iloc[0]
    assert b_cell["status"] == "ok"
    assert pd.isna(b_cell["reason"])
    assert b_cell["n_responders"] == 4
    assert b_cell["n_nonresponders"] == 4
    assert b_cell["median_responders"] == pytest.approx(11.5)
    assert b_cell["median_nonresponders"] == pytest.approx(2.5)

    cd8 = out[out["population"] == "cd8_t_cell"].iloc[0]
    assert cd8["status"] == "unavailable"
    assert cd8["reason"] == "no non-responders (response = no) at this timepoint"
    assert math.isnan(cd8["p_raw"])

    # populations with no rows at all for day 0.
    for population in POPULATIONS:
        if population in ("b_cell", "cd8_t_cell"):
            continue
        row = out[out["population"] == population].iloc[0]
        assert row["status"] == "unavailable"
        assert row["reason"] == "no samples match this cohort at this timepoint"


def test_compare_cells_missing_responders_reason():
    rows = [("nk_cell", 7, "s0", "no", 1.0), ("nk_cell", 7, "s1", "no", 2.0)]
    out = stats.compare_cells(_points(rows), [7])
    row = out[out["population"] == "nk_cell"].iloc[0]
    assert row["status"] == "unavailable"
    assert row["reason"] == "no responders (response = yes) at this timepoint"


def test_compare_cells_flags_subject_duplication():
    rows = [
        ("monocyte", 0, "dup_subject", "yes", 10.0),
        ("monocyte", 0, "dup_subject", "no", 5.0),
    ]
    out = stats.compare_cells(_points(rows), [0])
    row = out[out["population"] == "monocyte"].iloc[0]
    assert row["status"] == "unavailable"
    assert row["reason"] == "a subject contributes more than one sample to this test"


def test_compare_cells_never_raises_on_empty_groups():
    out = stats.compare_cells(_points([]), [0, 7, 14])
    assert isinstance(out, pd.DataFrame)


def test_adjust_family_bh_over_ok_rows_only():
    cells = pd.DataFrame([
        {"population": "b_cell", "time_from_treatment_start": 0, "status": "ok", "reason": None, "p_raw": 0.01},
        {"population": "cd8_t_cell", "time_from_treatment_start": 0, "status": "ok", "reason": None, "p_raw": 0.02},
        {"population": "cd4_t_cell", "time_from_treatment_start": 0, "status": "ok", "reason": None, "p_raw": 0.9},
        {"population": "nk_cell", "time_from_treatment_start": 0, "status": "unavailable",
         "reason": "no samples match this cohort at this timepoint", "p_raw": None},
    ])
    out = stats.adjust_family(cells)
    assert out["p_adj"].tolist()[:3] == pytest.approx([0.03, 0.03, 0.9])
    assert math.isnan(out["p_adj"].iloc[3])
    assert out["significant"].tolist() == [1, 1, 0, 0]
    assert stats.family_size(cells) == 3
    # adjust_family must not mutate the input.
    assert "p_adj" not in cells.columns


def test_adjust_family_all_unavailable_yields_empty_family():
    cells = pd.DataFrame([
        {"population": "b_cell", "time_from_treatment_start": 0, "status": "unavailable",
         "reason": "no samples match this cohort at this timepoint", "p_raw": None},
    ])
    out = stats.adjust_family(cells)
    assert math.isnan(out["p_adj"].iloc[0])
    assert out["significant"].tolist() == [0]
    assert stats.family_size(cells) == 0
