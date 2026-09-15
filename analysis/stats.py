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
CELL_COLUMNS = [
    "population", "time_from_treatment_start", "n_responders", "n_nonresponders",
    "median_responders", "median_nonresponders", "u_statistic", "p_raw", "effect_size", "status", "reason",
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


_UNAVAILABLE_STATS = {
    "median_responders": None,
    "median_nonresponders": None,
    "u_statistic": None,
    "p_raw": None,
    "effect_size": None,
}


def compare_cells(points: pd.DataFrame, timepoints: Sequence[int]) -> pd.DataFrame:
    """One row per population (POPULATIONS order) per timepoint (given order).

    Never raises: a cell that cannot be tested is recorded as unavailable with a reason instead of
    running the comparison. `points` may be empty but must still carry the `population`,
    `time_from_treatment_start`, `subject`, `response` and `percentage` columns.
    """
    records = []
    for population in POPULATIONS:
        for day in timepoints:
            day = int(day)
            cell = points[(points["population"] == population) & (points["time_from_treatment_start"] == day)]
            responders = cell.loc[cell["response"] == "yes", "percentage"]
            nonresponders = cell.loc[cell["response"] == "no", "percentage"]
            base = {
                "population": population,
                "time_from_treatment_start": day,
                "n_responders": int(len(responders)),
                "n_nonresponders": int(len(nonresponders)),
                **_UNAVAILABLE_STATS,
            }
            if cell.empty:
                records.append({**base, "status": "unavailable", "reason": "no samples match this cohort at this timepoint"})
            elif cell["subject"].duplicated().any():
                records.append({**base, "status": "unavailable", "reason": "a subject contributes more than one sample to this test"})
            elif responders.empty:
                records.append({**base, "status": "unavailable", "reason": "no responders (response = yes) at this timepoint"})
            elif nonresponders.empty:
                records.append({**base, "status": "unavailable", "reason": "no non-responders (response = no) at this timepoint"})
            else:
                comparison = compare_groups(responders, nonresponders)
                records.append({**base, **comparison.__dict__, "status": "ok", "reason": None})
    return pd.DataFrame.from_records(records, columns=CELL_COLUMNS)


def adjust_family(cells: pd.DataFrame) -> pd.DataFrame:
    """Copy of `cells` with `p_adj` (BH over the ok rows, in row order; NaN elsewhere) and `significant`."""
    frame = cells.copy()
    ok = frame["status"] == "ok"
    p_adj = pd.Series(float("nan"), index=frame.index, dtype=float)
    if ok.any():
        p_adj.loc[ok] = benjamini_hochberg(frame.loc[ok, "p_raw"])
    frame["p_adj"] = p_adj
    frame["significant"] = (ok & (frame["p_adj"] < ALPHA)).astype(int)
    return frame


def family_size(cells: pd.DataFrame) -> int:
    return int((cells["status"] == "ok").sum())
