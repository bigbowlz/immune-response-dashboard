"""Statistics for the pipeline: relative frequencies, per-timepoint Mann-Whitney U, BH correction, Cliff's delta.

Only the pipeline imports this module; the API must stay free of pandas and scipy.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from scipy import stats as sps

from analysis.schema import POPULATIONS

ALPHA = 0.05
SUMMARY_COLUMNS = ["sample", "total_count", "population", "count", "percentage"]
STATS_COLUMNS = [
    "population", "time_from_treatment_start", "n_responders", "n_nonresponders",
    "median_responders", "median_nonresponders", "u_statistic", "p_raw", "p_adj", "effect_size", "significant",
]


def compute_sample_summary(cell_counts: pd.DataFrame) -> pd.DataFrame:
    """Part 2: one row per sample per population with the count as a percentage of the sample total."""
    frame = cell_counts[["sample", "population", "count"]].copy()
    frame["total_count"] = frame.groupby("sample")["count"].transform("sum")
    zero_total = frame.loc[frame["total_count"] <= 0, "sample"].unique()
    if len(zero_total):
        raise ValueError(f"samples with zero total cell count, percentage undefined: {sorted(zero_total)[:5]}")
    frame["percentage"] = frame["count"] / frame["total_count"] * 100
    frame["population"] = pd.Categorical(frame["population"], categories=list(POPULATIONS), ordered=True)
    frame = frame.sort_values(["sample", "population"]).reset_index(drop=True)
    frame["population"] = frame["population"].astype(str)
    return frame[SUMMARY_COLUMNS]


@dataclass(frozen=True)
class GroupComparison:
    n_responders: int
    n_nonresponders: int
    median_responders: float
    median_nonresponders: float
    u_statistic: float
    p_raw: float
    effect_size: float  # Cliff's delta, positive when responders are higher


def compare_groups(responders: Sequence[float], nonresponders: Sequence[float]) -> GroupComparison:
    responders = list(responders)
    nonresponders = list(nonresponders)
    if not responders or not nonresponders:
        raise ValueError(f"cannot compare groups: one group is empty (responders={len(responders)}, nonresponders={len(nonresponders)})")
    result = sps.mannwhitneyu(responders, nonresponders, alternative="two-sided")
    n1, n2 = len(responders), len(nonresponders)
    delta = 2 * float(result.statistic) / (n1 * n2) - 1
    return GroupComparison(
        n_responders=n1,
        n_nonresponders=n2,
        median_responders=float(pd.Series(responders).median()),
        median_nonresponders=float(pd.Series(nonresponders).median()),
        u_statistic=float(result.statistic),
        p_raw=float(result.pvalue),
        effect_size=delta,
    )


def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    return [float(p) for p in sps.false_discovery_control(list(pvalues), method="bh")]


def compare_response_groups(points: pd.DataFrame) -> pd.DataFrame:
    """Part 3: responders vs non-responders, tested separately for every population at every timepoint."""
    records = []
    timepoints = sorted(points["time_from_treatment_start"].unique())
    for population in POPULATIONS:
        for day in timepoints:
            cell = points[(points["population"] == population) & (points["time_from_treatment_start"] == day)]
            try:
                comparison = compare_groups(
                    cell.loc[cell["response"] == "yes", "percentage"],
                    cell.loc[cell["response"] == "no", "percentage"],
                )
            except ValueError as exc:
                raise ValueError(f"{population} at day {day}: {exc}") from exc
            records.append({"population": population, "time_from_treatment_start": int(day), **comparison.__dict__})
    frame = pd.DataFrame.from_records(records)
    frame["p_adj"] = benjamini_hochberg(frame["p_raw"])
    frame["significant"] = (frame["p_adj"] < ALPHA).astype(int)
    return frame[STATS_COLUMNS]
