export type Population = "b_cell" | "cd8_t_cell" | "cd4_t_cell" | "nk_cell" | "monocyte";
export const POPULATIONS: Population[] = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"];
export const POPULATION_LABELS: Record<Population, string> = {
  b_cell: "B cells",
  cd8_t_cell: "CD8 T cells",
  cd4_t_cell: "CD4 T cells",
  nk_cell: "NK cells",
  monocyte: "Monocytes",
};

export interface SummaryRow {
  sample: string;
  total_count: number;
  population: Population;
  count: number;
  percentage: number;
}
export interface SummaryResponse { rows: SummaryRow[]; total: number; limit: number; offset: number }
export type SummaryColumn = keyof SummaryRow;
// A type alias, not an interface: aliases get an implicit index signature, so it can be passed to `query()` below.
export type FrequencyQuery = { search?: string; sort?: SummaryColumn; dir?: "asc" | "desc"; limit?: number; offset?: number };

export interface Health {
  status: string;
  db_path: string;
  tables: Record<string, number>;
  meta: Partial<Record<"generated_at" | "csv_sha256" | "csv_rows" | "python_version" | "pandas_version" | "scipy_version", string>>;
}

/** The five selectors that define a cohort. The API takes each as "all" or one of the data's values. */
export type CohortFilterKey = "condition" | "treatment" | "sample_type" | "project" | "time_from_treatment_start";
export type CohortFilters = Record<CohortFilterKey, string>; // always strings in the UI, "all" included
export type CohortOptions = Record<CohortFilterKey, Array<string | number>>;

export interface BreakdownRow { category: string | number; n_samples: number; n_subjects: number; pct_samples: number }
export type BreakdownKey = "project" | "response" | "sex" | "time_from_treatment_start";

export interface CohortSummary {
  filters: CohortFilters;
  n_samples: number;
  n_subjects: number;
  n_missing_response: number;
  breakdowns: Record<BreakdownKey, BreakdownRow[]>;
}

/** One population x timepoint cell. Every statistic is null when `status` is "unavailable". */
export interface CohortStat {
  condition: string;
  treatment: string;
  sample_type: string;
  project: string;
  timepoints: string;
  population: Population;
  time_from_treatment_start: number;
  n_responders: number;
  n_nonresponders: number;
  median_responders: number | null;
  median_nonresponders: number | null;
  u_statistic: number | null;
  p_raw: number | null;
  p_adj: number | null;
  effect_size: number | null;
  significant: 0 | 1;
  status: "ok" | "unavailable";
  reason: string | null;
}

export interface CohortStatsResponse {
  filters: CohortFilters;
  family: string;
  rows: CohortStat[];
  alpha: number;
  n_tests: number;
  n_samples: number;
  n_subjects: number;
  n_missing_response: number;
}

export interface CohortPoint {
  sample: string;
  subject: string;
  population: Population;
  time_from_treatment_start: number;
  response: "yes" | "no";
  percentage: number;
}
export interface CohortPointsResponse { points: CohortPoint[] }

export interface SampleRow {
  sample: string;
  subject: string;
  project: string;
  condition: string;
  treatment: string;
  sample_type: string;
  time_from_treatment_start: number;
  response: string | null;
  sex: string;
}
export type SampleColumn = keyof SampleRow;
export interface SamplesResponse { rows: SampleRow[]; total: number; limit: number; offset: number }
