# Immune Response Dashboard

Explore how immune cell populations differ between responders and non-responders in a clinical trial dataset.

Live dashboard: https://immune-response-dashboard.vercel.app (the same app that `make dashboard` serves locally at http://localhost:8000)

![Dashboard](docs/dashboard.png)

## What it shows

- **Cohort analysis** — pick a cohort with five filters, then read its composition, per-population boxplots of cell frequency by day split by response, the statistics behind each panel, and the list of matching samples.
- **Cell frequencies** — a searchable, sortable, exportable table of every sample's relative cell-population frequencies.

In the default cohort — melanoma patients treated with miraclib, PBMC samples, all projects, all timepoints, 1,968 samples from 656 subjects — no population separates responders from non-responders after multiple-comparison correction; the largest differences (B cells lower in responders at day 14, adjusted p 0.216, and CD4 T cells higher at day 7, 0.223) do not reach significance.

### Cohort analysis page

Five filters define the cohort, each taking `all` or one value from the data:

| Filter      | Values                            | Default  |
| ----------- | --------------------------------- | -------- |
| Condition   | all, melanoma, carcinoma, healthy | melanoma |
| Treatment   | all, miraclib, phauximab, none    | miraclib |
| Sample type | all, PBMC, WB                     | PBMC     |
| Project     | all, prj1, prj2, prj3             | all      |
| Timepoints  | all, 0, 7, 14                     | all      |

"Baseline only" sets timepoints to day 0 and leaves the other four alone; "Reset to default cohort" restores all five defaults. A cohort is the selected group of samples and their subjects, never an individual subject or sample. Below the charts and the statistics table, "Matching samples" lists every sample in the cohort — sample, subject, project, condition, treatment, sample type, timepoint, response and sex — with sorting and paging, and "Export CSV" downloads every matching row, not just the page on screen.

With every filter widened to "all" the cohort is the whole dataset: 10,500 samples from 3,500 subjects, 1,422 of them without a recorded response. Those are the samples of the 474 untreated healthy subjects; the page counts them and says how many there are instead of putting them in the comparison.

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

| Symptom or need                           | What to do                                                                     |
| ----------------------------------------- | ------------------------------------------------------------------------------ |
| Dashboard says "No pipeline output found" | `make pipeline`, then reload                                                   |
| Port 8000 is busy                         | `PORT=8001 make dashboard`                                                     |
| Frontend changed but the page looks stale | `REBUILD=1 make dashboard`                                                     |
| Use another interpreter or database path  | `PYTHON=/path/to/python`, `CELL_COUNTS_DB=/path/to.db` (the API also reads it) |
| Run the API without the built frontend    | `SERVE_FRONTEND=0`                                                             |

## How it is built

| Layer                  | Responsibility                                                                                                                                                                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline (`analysis/`) | Reads the raw tables, runs the statistics for every selectable cohort, writes the result tables into `cell_counts.db`                                                                                                                                      |
| API (`server/`)        | Reads the pipeline's result tables, and for the selected cohort's filters runs COUNT/GROUP BY queries over the raw sample and subject tables to count, break down and list the matching samples; never imports pandas or scipy, never computes a statistic |
| Frontend (`frontend/`) | Fetches from the API and renders the two pages                                                                                                                                                                                                             |

**Schema** — three raw tables plus five result tables in `cell_counts.db`:

- `subjects` — one row per subject: project, condition, age, sex, treatment, response
- `samples` — one row per sample: subject, sample type, day (`time_from_treatment_start`)
- `cell_counts` — one row per sample per population: raw count
- `sample_summary` — one row per sample per population: count as a percentage of that sample's total
- `response_stats` — one row per cohort key (condition, treatment, sample type, project) per correction family (`timepoints`: `all`, `0`, `7` or `14`) per population per day: Mann-Whitney U, raw and BH-adjusted p, Cliff's delta, significance. A cell that could not be tested carries NULL statistics with `status = 'unavailable'` and a `reason`
- `response_strata` — one row per cohort key per correction family: `n_samples`, `n_subjects`, `n_missing_response`, `n_tests` (the valid tests the correction ran across)
- `cohort_summary` — the default cohort's baseline sample and subject counts by project, response and sex; a static answer kept for direct SQL inspection, while the cohort endpoints recompute counts for user-chosen filters
- `pipeline_meta` — provenance of the last pipeline run: `generated_at`, `csv_sha256`, `csv_rows`, `python_version`, `pandas_version`, `scipy_version`

**API** (all `GET`, under `/api`):

| Path                                                 | Returns                                                                                                                                   |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/health`                                        | Row counts per table plus the `pipeline_meta` provenance                                                                                  |
| `/api/frequencies?search=&sort=&dir=&limit=&offset=` | One page of the cell-frequency table (`limit` 1–500, default 50; `offset` default 0); sorted and searched in SQL so a page stays a few KB |
| `/api/frequencies.csv?search=&sort=&dir=`            | The same table as a full CSV, every matching row, streamed                                                                                |
| `/api/cohort/options`                                | The distinct filter values available                                                                                                      |
| `/api/cohort/summary?…`                              | Sample and subject counts, how many matching samples have no recorded response, and breakdowns by project, response, sex and timepoint    |
| `/api/cohort/stats?…`                                | The cohort's `response_stats` rows including unavailable ones, the correction `family` they belong to, and `n_tests`                      |
| `/api/cohort/points?…`                               | Per-sample percentages behind the boxplots, for the samples with a recorded response                                                      |
| `/api/cohort/samples?…&sort=&dir=&limit=&offset=`    | One page of the matching samples (`limit` 1–500, default 50; `offset` default 0)                                                          |
| `/api/cohort/samples.csv?…&sort=&dir=`               | Every matching sample as CSV, streamed                                                                                                    |

Each cohort endpoint takes the same five filters as query parameters — `condition`, `treatment`, `sample_type`, `project`, `time_from_treatment_start` — each `all` or one value from the data. An omitted parameter falls back to the default listed above; an unknown value is a 422.

**Three requirements files**: `requirements.txt` (fastapi, uvicorn) is API-only because the hosted Python function installs from just this file — the split is a hosting decision, not a doctrine. `requirements-pipeline.txt` (pandas, scipy) is needed only to run the pipeline locally; `requirements-dev.txt` (pytest, httpx, httpx2) is needed only to run the tests.

The hosted copy serves a `cell_counts.db` committed to the repo; a local run regenerates it, so `make pipeline` modifies that tracked file — expected, not a mistake.

## Analysis choices

**Denominator.** The five populations' counts sum to a sample's total; every percentage in the dashboard is labelled "Percent of total" and means count divided by that sum.

**Per-timepoint tests.** Every subject in the dataset has exactly three samples, one per timepoint (day 0, 7, 14), and one condition, treatment, sample type and project, so whatever the filters, a subject contributes at most one sample to any population×timepoint comparison. Pooling the three days into one test would instead treat each person as three independent observations. So Mann-Whitney U runs separately for each of the 5 populations at each selected day — 15 tests when all three days are selected, 5 for a single day — one sample per subject per test. The pipeline re-checks that one-sample-per-subject condition for every cell it computes and marks the cell unavailable rather than testing it if the check ever fails. A naive pooled test across all 1,968 samples of the default cohort gives CD4 T cells p = 0.013; that number is exactly the double-counting the per-timepoint design is built to avoid, and it is not reported as a result.

**Multiple comparisons.** There is one correction rule. Benjamini-Hochberg is applied once across every valid population×timepoint test in the selected cohort and timepoint selection: up to 15 tests with all timepoints selected, up to 5 with one, and the dashboard states how many valid tests the correction actually ran across. Significant means adjusted p < 0.05. A cell that cannot be tested — no samples match, no recorded responses, one of the two response groups missing, or a subject contributing more than one sample — carries no p-value, is listed with its reason, and is not counted as a non-significant test. Benjamini-Hochberg is the standard false-discovery-rate control for a family of tests like this one. The five percentages of a sample sum to 100, so the tests are not independent; BH's dependence assumptions are stated here, not established by this data.

**Precomputed cohorts.** The pipeline enumerates all 4 × 4 × 3 × 4 = 192 cohort keys over condition, treatment, sample type and project, computes each key's 15 population×timepoint cells once (2,880 Mann-Whitney U tests) and then forms four correction families per key — all timepoints, and day 0, 7 and 14 on their own. That is 5,760 `response_stats` rows over 768 `response_strata` rows, written in about seven seconds. Changing a filter therefore selects an already-corrected family instead of recomputing one, and the numbers on screen are the numbers the pipeline wrote.

**Effect size.** Cliff's delta (2U / (n1·n2) − 1), positive when responders are higher. A p-value is never reported without it, so a small but "significant" difference can't be read as a large one.

**Baseline and post-treatment days.** Day 0 samples are taken before treatment, so a day-0 difference is an association with the response recorded later, not evidence that the population predicts it. Day 7 and day 14 samples are taken after treatment started, so a difference there describes how the two response groups already differ; by itself it shows neither prediction nor that the treatment caused the difference. The page says which of the two a reader is looking at, and "Baseline only" narrows the cohort to day 0 in one click.

`response_stats` for the default cohort (melanoma, miraclib, PBMC, all projects) with all timepoints selected, so the Benjamini-Hochberg correction runs across these 15 tests:

| Population | Day | n resp. | n non-resp. | Median resp. | Median non-resp. | p (raw) | p (adjusted) | Cliff's delta | Significant |
| ---------- | --- | ------- | ----------- | ------------ | ---------------- | ------- | ------------ | ------------- | ----------- |
| b_cell     | 0   | 331     | 325         | 9.79         | 9.76             | 0.5485  | 0.8089       | 0.027         | no          |
| cd4_t_cell | 0   | 331     | 325         | 29.63        | 29.53            | 0.7964  | 0.8533       | 0.012         | no          |
| cd8_t_cell | 0   | 331     | 325         | 24.4         | 24.6             | 0.5140  | 0.8089       | -0.029        | no          |
| monocyte   | 0   | 331     | 325         | 19.61        | 20.29            | 0.2114  | 0.5285       | -0.056        | no          |
| nk_cell    | 0   | 331     | 325         | 15.0         | 14.89            | 0.8853  | 0.8853       | -0.007        | no          |
| b_cell     | 7   | 331     | 325         | 9.23         | 9.97             | 0.1439  | 0.4316       | -0.066        | no          |
| cd4_t_cell | 7   | 331     | 325         | 30.45        | 29.55            | 0.0297  | 0.2228       | 0.098         | no          |
| cd8_t_cell | 7   | 331     | 325         | 24.7         | 24.77            | 0.6377  | 0.8089       | -0.021        | no          |
| monocyte   | 7   | 331     | 325         | 19.6         | 20.03            | 0.4841  | 0.8089       | -0.032        | no          |
| nk_cell    | 7   | 331     | 325         | 14.42        | 14.8             | 0.1378  | 0.4316       | -0.067        | no          |
| b_cell     | 14  | 331     | 325         | 9.11         | 9.84             | 0.0144  | 0.2162       | -0.110        | no          |
| cd4_t_cell | 14  | 331     | 325         | 30.79        | 30.07            | 0.0755  | 0.3774       | 0.080         | no          |
| cd8_t_cell | 14  | 331     | 325         | 25.08        | 24.56            | 0.7407  | 0.8533       | 0.015         | no          |
| monocyte   | 14  | 331     | 325         | 19.62        | 19.75            | 0.6471  | 0.8089       | -0.021        | no          |
| nk_cell    | 14  | 331     | 325         | 14.35        | 14.65            | 0.3147  | 0.6744       | -0.045        | no          |

The honest result is a null: nothing reaches adjusted p < 0.05. The two smallest adjusted p-values are both around 0.22 — b_cell at day 14 (0.2162, lower in responders) and cd4_t_cell at day 7 (0.2228, higher in responders).

**Project as a filter.** The default cohort spans two projects (prj1: 195 responders and 189 non-responders; prj3: 136 and 136), and selecting one of them selects that cohort's own precomputed family with its own BH correction rather than re-slicing the pooled numbers. The result is null within each project too — the smallest adjusted p is 0.400 in prj1 (b_cell, day 14) and 0.560 in prj3 (monocyte, day 0). Those results are consistent with the pooled one; that is all that can be said, since they do not rule out confounding or an effect masked inside a project.

**Limitations.** The comparison is not stratified by sex or age, which would be the next checks to run if any population had shown a signal. Cohorts are limited to the five selectors, since those are the combinations the pipeline precomputes. And a null result across a family of small effects is not evidence that no difference exists; it is evidence that this dataset does not show one.

**Baseline note.** At baseline every subject contributes exactly one sample, so sample and subject counts coincide (656 and 656 in the default cohort). The underlying query still counts distinct subjects rather than assuming this, and the cohort analysis page shows both counts for every breakdown.

## Design notes

Each view is laid out for the question it answers. One cohort analysis page now carries what used to be two separate views, a comparison page and a cohort-composition page, because the filters that define a cohort also define the comparison: the composition cards, the charts, the statistics and the sample list all describe the same selection. Population frequencies are per-population boxplots with time on the x-axis and response as the grouping, so both groups' spread at each day is visible at a glance. Per-timepoint adjusted p-values sit in a statistics table directly under the charts, so significance is read together with the plot rather than looked up elsewhere. Cohort breakdowns are metadata cards showing both sample and subject counts, because the two differ once several timepoints are included. Summary data is a searchable, exportable table, for a reader who wants one specific row rather than the whole picture. Built with Plotly and React.

**Where this differs**, and why:

| Convention                                     | This dashboard                                                                                                                       | Reason                                                                                                                                   |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| A single p-value next to each timepoint        | Raw p, BH-adjusted p, Cliff's delta and n per group in a statistics table under the charts                                           | A family of up to 15 tests needs correction, and a p-value alone doesn't say whether a difference is large enough to matter              |
| A response group for unrecorded/unknown status | Only responder and non-responder in the comparison; the page says how many matching samples have no recorded response                | A sample with no recorded response cannot go on either side of the test, so it is counted and named rather than plotted as a third group |
| A selectable denominator                       | One fixed denominator, labelled "Percent of total"                                                                                   | The dataset has only five populations; the label states exactly what is being divided                                                    |
| Named study visits                             | Numeric days (0, 7, 14), with day 0 labelled baseline                                                                                | That's what the data carries, and it separates a pre-treatment association from a post-treatment difference                              |
| A static cohort overview                       | Five filters sit above the metadata cards, the charts, the statistics and the sample list                                            | The task asks for a cohort a reader can widen or narrow, not a fixed summary                                                             |
| —                                              | The overview table shows the Part 2 percentage-of-total summary                                                                      | The table's shape follows the assignment, not a separate convention                                                                      |
| Repeated measures left implicit                | Both the dashboard text and this README say each subject contributes one sample per timepoint and that tests run per timepoint       | Makes the independence assumption a reader can check, since it's the main statistical trap in this data                                  |
| No timepoint singled out                       | Day 0 differences are described as baseline associations, day 7 and 14 as post-treatment differences                                 | Naming what each day can and cannot support keeps the reading of the chart honest                                                        |
| A filter only redraws the chart                | Every filter re-selects a precomputed correction family, so the statistics and their BH correction always match the cohort on screen | Correcting per cohort is the only way a cohort's numbers stay internally consistent, and precomputing every key keeps it instant         |

[![CI](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml)

## License

MIT — see [LICENSE](LICENSE).
