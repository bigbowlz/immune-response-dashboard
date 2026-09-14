# Immune Response Dashboard

Explore how immune cell populations differ between responders and non-responders in a clinical trial dataset.

Live dashboard: https://immune-response-dashboard.vercel.app (the same app that `make dashboard` serves locally at http://localhost:8000)

![Dashboard](docs/dashboard.png)

## What it shows

- **Responder comparison** — per-population boxplots of cell frequency by day, with the Mann-Whitney U statistics behind each panel.
- **Cell frequencies** — a searchable, sortable, exportable table of every sample's relative cell-population frequencies.
- **Cohort subsets** — filterable sample and subject counts by project, response and sex.

No population separates responders from non-responders after multiple-comparison correction; the largest early-treatment signals (B cells lower and CD4 T cells higher in responders at day 14 and day 7) do not reach significance.

## Run it

Prerequisites: Python 3.12+, Node 20+ with npm, make.

```bash
make setup      # creates .venv, installs Python and frontend dependencies, builds the frontend
make pipeline   # python load_data.py, then python -m analysis.pipeline; writes cell_counts.db
make dashboard  # serves API + dashboard at http://localhost:8000
```

**GitHub Codespaces**: Code -> Create codespace, wait for setup to finish (about two minutes after the codespace opens), run the three commands above, then click "Open in Browser" on the port 8000 notification.

Tests: `.venv/bin/python -m pytest`. Interactive API docs: `http://localhost:8000/api/docs`. `python load_data.py` alone creates the database with the raw tables and empty result tables.

### Options and troubleshooting

| Symptom or need | What to do |
|---|---|
| Dashboard says "No pipeline output found" | `make pipeline`, then reload |
| Port 8000 is busy | `PORT=8001 make dashboard` |
| Frontend changed but the page looks stale | `REBUILD=1 make dashboard` |
| Use another interpreter or database path | `PYTHON=/path/to/python`, `CELL_COUNTS_DB=/path/to.db` (the API also reads it) |
| Run the API without the built frontend | `SERVE_FRONTEND=0` |

## How it is built

| Layer | Responsibility |
|---|---|
| Pipeline (`analysis/`) | Reads the raw tables, runs the statistics, writes the result tables into `cell_counts.db` |
| API (`server/`) | Reads the pipeline's result tables, and for the cohort explorer's user-chosen filters runs COUNT/GROUP BY queries over the raw sample and subject tables; never imports pandas or scipy, never computes a statistic |
| Frontend (`frontend/`) | Fetches from the API and renders the three pages |

**Schema** — three raw tables plus four result tables in `cell_counts.db`:

- `subjects` — one row per subject: project, condition, age, sex, treatment, response
- `samples` — one row per sample: subject, sample type, day (`time_from_treatment_start`)
- `cell_counts` — one row per sample per population: raw count
- `sample_summary` — one row per sample per population: count as a percentage of that sample's total
- `response_stats` — one row per population per day per stratum: Mann-Whitney U, raw and BH-adjusted p, Cliff's delta, significance
- `cohort_summary` — baseline-cohort sample and subject counts by project, response and sex; a static answer kept for direct SQL inspection, while `/api/subsets` recomputes counts for user-chosen filters
- `pipeline_meta` — provenance of the last pipeline run: `generated_at`, `csv_sha256`, `csv_rows`, `python_version`, `pandas_version`, `scipy_version`

**API** (all `GET`, under `/api`):

| Path | Returns |
|---|---|
| `/api/health` | Row counts per table plus the `pipeline_meta` provenance |
| `/api/frequencies?search=&sort=&dir=&limit=&offset=` | One page of the cell-frequency table (`limit` 1–500, default 50; `offset` default 0); sorted and searched in SQL so a page stays a few KB |
| `/api/frequencies.csv?search=&sort=&dir=` | The same table as a full CSV, every matching row, streamed |
| `/api/response/stats?project=all` | The 15 `response_stats` rows for one stratum (`all` or a project id) |
| `/api/response/samples?project=all` | Per-sample percentages behind the boxplots, for that stratum |
| `/api/subsets/options` | The distinct filter values available |
| `/api/subsets?condition=&treatment=&sample_type=&time_from_treatment_start=` | Sample/subject counts and breakdowns for a filter combination |

**Three requirements files**: `requirements.txt` (fastapi, uvicorn) is API-only because the hosted Python function installs from just this file — the split is a hosting decision, not a doctrine. `requirements-pipeline.txt` (pandas, scipy) is needed only to run the pipeline locally; `requirements-dev.txt` (pytest, httpx, httpx2) is needed only to run the tests.

The hosted copy serves a `cell_counts.db` committed to the repo; a local run regenerates it, so `make pipeline` modifies that tracked file — expected, not a mistake.

## Analysis choices

**Denominator.** The five populations' counts sum to a sample's total; every percentage in the dashboard is labelled "Percent of total" and means count divided by that sum.

**Per-timepoint tests.** Every subject in the response cohort has exactly three samples (day 0, 7, 14). Pooling all three into one test would treat each person as three independent observations. Instead, Mann-Whitney U runs separately for each of the 5 populations at each of the 3 days — 15 tests, one sample per subject per test. A naive pooled test across all 1,968 samples gives CD4 T cells p = 0.013; that number is exactly the double-counting the per-timepoint design is built to avoid, and it is not reported as a result.

**Multiple comparisons.** Benjamini-Hochberg is applied across the 15 tests of each stratum; significant means adjusted p < 0.05. The five percentages of a sample sum to 100, so the tests are not fully independent — BH is robust to this kind of positive dependence.

**Effect size.** Cliff's delta (2U / (n1·n2) − 1), positive when responders are higher. A p-value is never reported without it, so a small but "significant" difference can't be read as a large one.

**Baseline headlined.** The stated aim is predicting response, and only a day-0 measurement is available before anyone has been treated — days 7 and 14 describe treatment effects, not prediction.

`response_stats` for the whole cohort (`project = 'all'`):

| Population | Day | n resp. | n non-resp. | Median resp. | Median non-resp. | p (raw) | p (adjusted) | Cliff's delta | Significant |
|---|---|---|---|---|---|---|---|---|---|
| b_cell | 0 | 331 | 325 | 9.79 | 9.76 | 0.5485 | 0.8089 | 0.027 | no |
| cd4_t_cell | 0 | 331 | 325 | 29.63 | 29.53 | 0.7964 | 0.8533 | 0.012 | no |
| cd8_t_cell | 0 | 331 | 325 | 24.4 | 24.6 | 0.5140 | 0.8089 | -0.029 | no |
| monocyte | 0 | 331 | 325 | 19.61 | 20.29 | 0.2114 | 0.5285 | -0.056 | no |
| nk_cell | 0 | 331 | 325 | 15.0 | 14.89 | 0.8853 | 0.8853 | -0.007 | no |
| b_cell | 7 | 331 | 325 | 9.23 | 9.97 | 0.1439 | 0.4316 | -0.066 | no |
| cd4_t_cell | 7 | 331 | 325 | 30.45 | 29.55 | 0.0297 | 0.2228 | 0.098 | no |
| cd8_t_cell | 7 | 331 | 325 | 24.7 | 24.77 | 0.6377 | 0.8089 | -0.021 | no |
| monocyte | 7 | 331 | 325 | 19.6 | 20.03 | 0.4841 | 0.8089 | -0.032 | no |
| nk_cell | 7 | 331 | 325 | 14.42 | 14.8 | 0.1378 | 0.4316 | -0.067 | no |
| b_cell | 14 | 331 | 325 | 9.11 | 9.84 | 0.0144 | 0.2162 | -0.110 | no |
| cd4_t_cell | 14 | 331 | 325 | 30.79 | 30.07 | 0.0755 | 0.3774 | 0.080 | no |
| cd8_t_cell | 14 | 331 | 325 | 25.08 | 24.56 | 0.7407 | 0.8533 | 0.015 | no |
| monocyte | 14 | 331 | 325 | 19.62 | 19.75 | 0.6471 | 0.8089 | -0.021 | no |
| nk_cell | 14 | 331 | 325 | 14.35 | 14.65 | 0.3147 | 0.6744 | -0.045 | no |

The honest result is a null: nothing reaches adjusted p < 0.05. The two smallest adjusted p-values are both around 0.22 — b_cell at day 14 (0.2162, lower in responders) and cd4_t_cell at day 7 (0.2228, higher in responders).

**Stratification by project.** The response cohort spans two projects (384 and 272 subjects), so the same 15 tests are also run within each project, each with its own BH correction, and the dashboard's project selector switches between these strata. The result is also null within each project — the smallest adjusted p is 0.400 in one project (b_cell, day 14) and 0.560 in the other (monocyte, day 0) — which rules out one project masking or manufacturing a signal that the pooled view would hide.

**Limitations.** The comparison is not stratified by sex or age. Those would be the next checks to run if any population had shown a signal.

**Baseline note.** At baseline every subject contributes exactly one sample, so sample and subject counts coincide (656 and 656). The underlying query still counts distinct subjects rather than assuming this, and the cohort-subsets page shows both counts for every breakdown.

## Design notes

Each view is laid out for the question it answers. Population frequencies are per-population boxplots with time on the x-axis and response as the grouping, so both groups' spread at each day is visible at a glance. Per-timepoint adjusted p-values are annotated directly on the chart, so significance is read together with the plot rather than looked up in a separate table. Cohort breakdowns are metadata cards showing both sample and subject counts, because the two differ once several timepoints are included. Summary data is a searchable, exportable table, for a reader who wants one specific row rather than the whole picture. Built with Plotly and React.

**Where this differs**, and why:

| Convention | This dashboard | Reason |
|---|---|---|
| A single p-value next to each timepoint | Raw p, BH-adjusted p, Cliff's delta and n per group in a stats table next to the chart | 15 tests need correction, and a p-value alone doesn't say whether a difference is large enough to matter |
| A response group for unrecorded/unknown status | Only responder and non-responder | The cohort is defined by having a recorded response, so no "unknown" group exists to show |
| A selectable denominator | One fixed denominator, labelled "Percent of total" | The dataset has only five populations; the label states exactly what is being divided |
| Named study visits | Numeric days (0, 7, 14), with day 0 labelled baseline | That's what the data carries, and it ties the chart to the stated goal of predicting response from baseline |
| A static cohort overview | Filters sit above the metadata cards | The task asks for a cohort a reader can widen or narrow, not a fixed summary |
| — | The overview table shows the Part 2 percentage-of-total summary | The table's shape follows the assignment, not a separate convention |
| Repeated measures left implicit | Both the dashboard text and this README say each subject contributes one sample per timepoint and that tests run per timepoint | Makes the independence assumption a reader can check, since it's the main statistical trap in this data |
| No timepoint singled out | Day 0 is headlined as the predictive result; days 7 and 14 are framed as treatment effects | Matches the stated aim of predicting response, which only a pre-treatment measurement can do |
| A filter only redraws the chart | The project selector re-runs the statistics (a fresh BH correction) for the selected stratum, not just a re-drawn chart | Recomputing per stratum is the only way project numbers stay internally consistent |

Also implemented: a "Same Y-axis across plots" toggle on the responder-comparison charts, for comparing panels on one scale when that's useful, off by default since each population has its own natural range.

## Verification

The test suite asserts the load and analysis numbers end to end:

- 10,500 samples from 3,500 subjects (3 samples each), 52,500 cell-count rows
- Response cohort: 1,968 samples from 656 subjects across days 0, 7 and 14
- Baseline cohort: 656 samples from 656 subjects
- Projects: prj1 384 subjects, prj3 272 subjects
- Response: 331 responders, 325 non-responders
- Sex: 344 male, 312 female

Every pipeline run also writes a `pipeline_meta` provenance row — the input CSV's sha256, its row count, and the Python, pandas and scipy versions used — so a given set of numbers can always be traced back to the run that produced them; `/api/health` reports the same values.

[![CI](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml)

## License

MIT — see [LICENSE](LICENSE).
