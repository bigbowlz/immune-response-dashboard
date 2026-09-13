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

export interface ResponseStat {
  project: string; // "all" or a project id
  population: Population;
  time_from_treatment_start: number;
  n_responders: number;
  n_nonresponders: number;
  median_responders: number;
  median_nonresponders: number;
  u_statistic: number;
  p_raw: number;
  p_adj: number;
  effect_size: number;
  significant: 0 | 1;
}
export interface ResponseStatsResponse { rows: ResponseStat[]; alpha: number; n_tests: number; project: string; projects: string[] }

export interface ResponsePoint {
  sample: string;
  subject: string;
  project: string;
  population: Population;
  time_from_treatment_start: number;
  response: "yes" | "no";
  percentage: number;
}
export interface ResponseSamplesResponse { points: ResponsePoint[] }

export interface BreakdownRow { category: string | number; n_samples: number; n_subjects: number; pct_samples: number }
export type FilterKey = "condition" | "treatment" | "sample_type" | "time_from_treatment_start";
export type SubsetFilters = Record<FilterKey, string>; // "all" or a value, always strings in the UI
export interface SubsetsResponse {
  filters: Record<FilterKey, string | number | null>;
  n_samples: number;
  n_subjects: number;
  breakdowns: Record<"project" | "response" | "sex" | "time_from_treatment_start", BreakdownRow[]>;
}
export type SubsetOptions = Record<FilterKey, Array<string | number>>;

export interface FormAnswer { question: string; n_samples: number; mean_b_cell: number }
