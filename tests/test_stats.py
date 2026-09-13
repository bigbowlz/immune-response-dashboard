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


def test_benjamini_hochberg_known_values():
    assert stats.benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05]) == pytest.approx([0.05] * 5)
    assert stats.benjamini_hochberg([0.001, 0.04, 0.5]) == pytest.approx([0.003, 0.06, 0.5])
    adjusted = stats.benjamini_hochberg([0.5, 0.001, 0.04])
    assert adjusted == pytest.approx([0.5, 0.003, 0.06])  # order preserved


def test_compare_response_groups_shape_and_correction():
    rows = []
    for population in POPULATIONS:
        for day in (0, 7, 14):
            for i in range(6):
                rows.append((population, day, "yes", 10 + i + (5 if population == "b_cell" and day == 0 else 0)))
                rows.append((population, day, "no", 10 + i))
    frame = pd.DataFrame(rows, columns=["population", "time_from_treatment_start", "response", "percentage"])
    out = stats.compare_response_groups(frame)
    assert len(out) == 15
    assert list(out.columns) == [
        "population", "time_from_treatment_start", "n_responders", "n_nonresponders",
        "median_responders", "median_nonresponders", "u_statistic", "p_raw", "p_adj", "effect_size", "significant",
    ]
    assert out["population"].tolist()[:3] == ["b_cell"] * 3
    assert out["time_from_treatment_start"].tolist()[:3] == [0, 7, 14]
    assert (out["p_adj"] >= out["p_raw"] - 1e-12).all()
    b0 = out[(out["population"] == "b_cell") & (out["time_from_treatment_start"] == 0)].iloc[0]
    assert b0["effect_size"] > 0.5
    assert b0["n_responders"] == 6
    assert set(out["significant"].unique()) <= {0, 1}
    assert not any(math.isnan(v) for v in out["p_adj"])


def test_compare_groups_rejects_empty_group():
    with pytest.raises(ValueError, match="empty"):
        stats.compare_groups([], [1, 2, 3])


def test_compare_response_groups_names_the_empty_cell():
    frame = pd.DataFrame(
        [("b_cell", 0, "no", 1.0), ("b_cell", 0, "no", 2.0)],
        columns=["population", "time_from_treatment_start", "response", "percentage"],
    )
    with pytest.raises(ValueError, match="b_cell.*day 0"):
        stats.compare_response_groups(frame)


def test_sample_summary_rejects_zero_total():
    counts = pd.DataFrame({"sample": ["s1"] * 5, "population": list(POPULATIONS), "count": [0] * 5})
    with pytest.raises(ValueError, match="s1"):
        stats.compute_sample_summary(counts)
