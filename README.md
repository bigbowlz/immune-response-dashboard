# Immune Response Dashboard

Explore how immune cell populations differ between responders and non-responders in a clinical trial dataset.

Live dashboard: https://immune-response-dashboard.vercel.app (the same app that `make dashboard` serves locally at http://localhost:8000)

![Dashboard](docs/dashboard.png)

## What it shows

- **Cohort analysis** — pick a cohort with five filters, then read its composition, a one-line finding, per-population boxplots of cell frequency by day split by response, the statistics behind each panel, and the list of matching samples.
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

The "Baseline only" switch sets timepoints to day 0 and leaves the other four alone; the "Default cohort" switch restores all five defaults. A cohort is the selected group of samples and their subjects, never an individual subject or sample.

Above the charts, one sentence names the population with the largest responder difference at the earliest selected day, says whether any test in the cohort is significant, and states how many tests the adjusted p-values are corrected for. Hovering a point on a boxplot shows that sample's count, population, sample and subject IDs and response; hovering a box shows its maximum, upper fence, quartiles, median, lower fence and minimum. The statistics table explains its U, BH-adjusted p, Cliff's delta and Significance columns in header tooltips. Below it, "Matching samples" lists every sample in the cohort — sample, subject, project, condition, treatment, sample type, timepoint, response and sex — with sorting and paging.

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
| Frontend (`frontend/`) | Fetches from the API and renders the two pages with React and Plotly                                                                                                                                                                                                            |

**Schema** — three raw tables and five result tables in `cell_counts.db`, declared in `analysis/schema.py`. `load_data.py` creates all eight and fills the raw ones from the CSV; the pipeline fills the result tables. The CSV repeats each subject's metadata on every row, so the loader normalises it into `subjects`, rejecting a subject whose metadata differs between rows, and keeps the per-sample fields in `samples`.

`subjects` — one row per subject

| Column      | Type    | Key | Meaning                                                     |
| ----------- | ------- | --- | ----------------------------------------------------------- |
| `subject`   | TEXT    | PK  | subject id                                                  |
| `project`   | TEXT    |     | prj1, prj2 or prj3                                          |
| `condition` | TEXT    |     | melanoma, carcinoma or healthy                              |
| `age`       | INTEGER |     | age in years                                                |
| `sex`       | TEXT    |     | M or F (checked)                                            |
| `treatment` | TEXT    |     | miraclib, phauximab or none                                 |
| `response`  | TEXT    |     | yes or no (checked); NULL when no response was recorded     |

`samples` — one row per sample, indexed on `subject`

| Column                      | Type    | Key                     | Meaning                    |
| --------------------------- | ------- | ----------------------- | -------------------------- |
| `sample`                    | TEXT    | PK                      | sample id                  |
| `subject`                   | TEXT    | FK → `subjects.subject` | subject the sample is from |
| `sample_type`               | TEXT    |                         | PBMC or WB                 |
| `time_from_treatment_start` | INTEGER |                         | day 0, 7 or 14             |

`cell_counts` — one row per sample per population

| Column       | Type    | Key                       | Meaning                                              |
| ------------ | ------- | ------------------------- | ---------------------------------------------------- |
| `sample`     | TEXT    | PK, FK → `samples.sample` |                                                      |
| `population` | TEXT    | PK                        | b_cell, cd8_t_cell, cd4_t_cell, nk_cell or monocyte  |
| `count`      | INTEGER |                           | raw cell count, checked ≥ 0                          |

`sample_summary` — one row per sample per population (the Part 2 table)

| Column        | Type    | Key                       | Meaning                                           |
| ------------- | ------- | ------------------------- | ------------------------------------------------- |
| `sample`      | TEXT    | PK, FK → `samples.sample` |                                                   |
| `total_count` | INTEGER |                           | sum of the five populations' counts in the sample |
| `population`  | TEXT    | PK                        |                                                   |
| `count`       | INTEGER |                           | raw cell count                                    |
| `percentage`  | REAL    |                           | `count` as a percentage of `total_count`          |

`response_stats` — one row per cohort key per correction family per population per day. The first seven columns form the primary key; the first four are each `all` or one value, and `timepoints` names the correction family: `all` (Benjamini-Hochberg across the three days' tests together) or `0`, `7` or `14` (across that day's tests only).

| Column                      | Type    | Key | Meaning                                                                                                  |
| --------------------------- | ------- | --- | -------------------------------------------------------------------------------------------------------- |
| `condition`                 | TEXT    | PK  | `all` or a condition                                                                                     |
| `treatment`                 | TEXT    | PK  | `all` or a treatment                                                                                     |
| `sample_type`               | TEXT    | PK  | `all` or a sample type                                                                                   |
| `project`                   | TEXT    | PK  | `all` or a project                                                                                       |
| `timepoints`                | TEXT    | PK  | correction family: `all`, `0`, `7` or `14`                                                               |
| `population`                | TEXT    | PK  |                                                                                                          |
| `time_from_treatment_start` | INTEGER | PK  | the day this test compares                                                                               |
| `n_responders`              | INTEGER |     | samples with response yes in the test                                                                    |
| `n_nonresponders`           | INTEGER |     | samples with response no in the test                                                                     |
| `median_responders`         | REAL    |     | median percentage among responders                                                                       |
| `median_nonresponders`      | REAL    |     | median percentage among non-responders                                                                   |
| `u_statistic`               | REAL    |     | Mann-Whitney U, responders against non-responders                                                        |
| `p_raw`                     | REAL    |     | two-sided p-value                                                                                        |
| `p_adj`                     | REAL    |     | Benjamini-Hochberg adjusted p within the family                                                          |
| `effect_size`               | REAL    |     | Cliff's delta, positive when responders are higher                                                       |
| `significant`               | INTEGER |     | 1 when `p_adj` < 0.05, else 0 (checked)                                                                  |
| `status`                    | TEXT    |     | `ok` or `unavailable` (checked); the six statistics above are NULL when unavailable                      |
| `reason`                    | TEXT    |     | why the cell could not be tested, NULL when `ok`                                                         |

`response_strata` — one row per cohort key per correction family

| Column               | Type    | Key | Meaning                                              |
| -------------------- | ------- | --- | ---------------------------------------------------- |
| `condition`          | TEXT    | PK  | `all` or a condition                                 |
| `treatment`          | TEXT    | PK  | `all` or a treatment                                 |
| `sample_type`        | TEXT    | PK  | `all` or a sample type                               |
| `project`            | TEXT    | PK  | `all` or a project                                   |
| `timepoints`         | TEXT    | PK  | correction family: `all`, `0`, `7` or `14`           |
| `n_samples`          | INTEGER |     | matching samples                                     |
| `n_subjects`         | INTEGER |     | distinct subjects among them                         |
| `n_missing_response` | INTEGER |     | matching samples with no recorded response           |
| `n_tests`            | INTEGER |     | valid tests the correction ran across in this family |

`cohort_summary` — the default cohort at baseline, broken down for direct SQL inspection (the API recomputes these counts for any filters)

| Column        | Type    | Key | Meaning                                            |
| ------------- | ------- | --- | -------------------------------------------------- |
| `breakdown`   | TEXT    | PK  | `project`, `response`, `sex` or `total`            |
| `category`    | TEXT    | PK  | the value within that breakdown                    |
| `n_samples`   | INTEGER |     | samples in the category                            |
| `n_subjects`  | INTEGER |     | distinct subjects in the category                  |
| `pct_samples` | REAL    |     | `n_samples` as a percentage of the cohort's samples |

`pipeline_meta` — provenance of the last pipeline run

| Column  | Type | Key | Meaning                                                                                         |
| ------- | ---- | --- | ----------------------------------------------------------------------------------------------- |
| `key`   | TEXT | PK  | `generated_at`, `csv_sha256`, `csv_rows`, `python_version`, `pandas_version` or `scipy_version` |
| `value` | TEXT |     |                                                                                                 |

**API** (all `GET`, under `/api`):

| Path                                                 | Returns                                                                                                                                   |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/health`                                        | Row counts per table plus the `pipeline_meta` provenance                                                                                  |
| `/api/frequencies?search=&sort=&dir=&limit=&offset=` | One page of the cell-frequency table (`limit` 1–500, default 50; `offset` default 0); sorted and searched in SQL so a page stays a few KB |
| `/api/frequencies.csv?search=&sort=&dir=`            | The same table as a full CSV, every matching row, streamed                                                                                |
| `/api/cohort/options`                                | The distinct filter values available                                                                                                      |
| `/api/cohort/summary?…`                              | Sample and subject counts, how many matching samples have no recorded response, and breakdowns by project, response, sex and timepoint (the page shows the first three) |
| `/api/cohort/stats?…`                                | The cohort's `response_stats` rows including unavailable ones, the correction `family` they belong to, and `n_tests`                      |
| `/api/cohort/points?…`                               | Per-sample percentages behind the boxplots, for the samples with a recorded response                                                      |
| `/api/cohort/samples?…&sort=&dir=&limit=&offset=`    | One page of the matching samples (`limit` 1–500, default 50; `offset` default 0)                                                          |

Each cohort endpoint takes the same five filters as query parameters — `condition`, `treatment`, `sample_type`, `project`, `time_from_treatment_start` — each `all` or one value from the data. An omitted parameter falls back to the default listed above; an unknown value is a 422.

**Three requirements files**: `requirements.txt` (fastapi, uvicorn) is API-only because the hosted Python function installs from just this file — the split is a hosting decision, not a doctrine. `requirements-pipeline.txt` (pandas, scipy) is needed only to run the pipeline locally; `requirements-dev.txt` (pytest, httpx, httpx2) is needed only to run the tests.

The hosted copy serves a `cell_counts.db` committed to the repo; a local run regenerates it, so `make pipeline` modifies that tracked file — expected, not a mistake.

## Analysis choices

**Per-timepoint tests.** Every subject in the dataset has exactly three samples, one per timepoint (day 0, 7, 14), and one condition, treatment, sample type and project, so whatever the filters, a subject contributes at most one sample to any population×timepoint comparison. Pooling the three days into one test would instead treat each person as three independent observations. So Mann-Whitney U runs separately for each of the 5 populations at each selected day — 15 tests when all three days are selected, 5 for a single day — one sample per subject per test. The pipeline re-checks that one-sample-per-subject condition for every cell it computes and marks the cell unavailable rather than testing it if the check ever fails. A naive pooled test across all 1,968 samples of the default cohort gives CD4 T cells p = 0.013; that number is exactly the double-counting the per-timepoint design is built to avoid, and it is not reported as a result.

**Multiple comparisons.** There is one correction rule. Benjamini-Hochberg is applied once across every valid population×timepoint test in the selected cohort and timepoint selection: up to 15 tests with all timepoints selected, up to 5 with one, and the statistics table's "p (BH-adjusted)" tooltip states how many valid tests the correction actually ran across. Significant means adjusted p < 0.05, as the "Significance" column's tooltip says. A cell that cannot be tested — no samples match, no recorded responses, one of the two response groups missing, or a subject contributing more than one sample — carries no p-value, is listed with its reason, and is not counted as a non-significant test. Benjamini-Hochberg is the standard false-discovery-rate control for a family of tests like this one. The five percentages of a sample sum to 100, so the tests are not independent; BH's dependence assumptions are stated here, not established by this data.

**Precomputed cohorts.** The pipeline enumerates all 4 × 4 × 3 × 4 = 192 cohort keys over condition, treatment, sample type and project, computes each key's 15 population×timepoint cells once (2,880 Mann-Whitney U tests) and then forms four correction families per key — all timepoints, and day 0, 7 and 14 on their own. That is 5,760 `response_stats` rows over 768 `response_strata` rows, written in about seven seconds. Changing a filter therefore selects an already-corrected family instead of recomputing one, and the numbers on screen are the numbers the pipeline wrote.

**Effect size.** Cliff's delta (2U / (n1·n2) − 1), positive when responders are higher. A p-value is never reported without it, so a small but "significant" difference can't be read as a large one.

**Baseline and post-treatment days.** Day 0 samples are taken before treatment, so a day-0 difference is an association with the response recorded later, not evidence that the population predicts it. Day 7 and day 14 samples are taken after treatment started, so a difference there describes how the two response groups already differ; by itself it shows neither prediction nor that the treatment caused the difference. The charts, the finding line and the "Baseline only" tooltip label day 0 as baseline, and that switch narrows the cohort to day 0 in one click.

**Project as a filter.** The default cohort spans two projects (prj1: 195 responders and 189 non-responders; prj3: 136 and 136), and selecting one of them selects that cohort's own precomputed family with its own BH correction rather than re-slicing the pooled numbers. The result is null within each project too — the smallest adjusted p is 0.400 in prj1 (b_cell, day 14) and 0.560 in prj3 (monocyte, day 0). Those results are consistent with the pooled one; that is all that can be said, since they do not rule out confounding or an effect masked inside a project.

**Limitations.** The comparison is not stratified by sex or age, which would be the next checks to run if any population had shown a signal. Cohorts are limited to the five selectors, since those are the combinations the pipeline precomputes. And a null result across a family of small effects is not evidence that no difference exists; it is evidence that this dataset does not show one.

**Baseline note.** At baseline every subject contributes exactly one sample, so sample and subject counts coincide (656 and 656 in the default cohort). The underlying query still counts distinct subjects rather than assuming this, and the cohort analysis page shows both counts for every breakdown.

[![CI](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/bigbowlz/immune-response-dashboard/actions/workflows/ci.yml)

## License

MIT — see [LICENSE](LICENSE).
