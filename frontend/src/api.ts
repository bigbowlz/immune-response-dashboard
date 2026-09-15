import type {
  CohortFilters, CohortOptions, CohortPointsResponse, CohortStatsResponse, CohortSummary,
  FrequencyQuery, Health, SampleColumn, SamplesResponse, SummaryResponse,
} from "./types";
import type { SortDir } from "./components/DataTable";

/** Thrown for any non-2xx response. `detail` is the API's own message when it sent one (e.g. "Run make pipeline first"). */
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail ?? detail; } catch { /* keep the status text */ }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const query = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") search.set(key, String(value));
  const s = search.toString();
  return s ? `?${s}` : "";
};

export const getHealth = () => getJson<Health>("/api/health");
export const getFrequencies = (q: FrequencyQuery, signal?: AbortSignal) => getJson<SummaryResponse>(`/api/frequencies${query(q)}`, signal);
export const frequenciesCsvUrl = (q: FrequencyQuery) => `/api/frequencies.csv${query({ search: q.search, sort: q.sort, dir: q.dir })}`;

export interface SamplePage { sort: SampleColumn; dir: SortDir; limit: number; offset: number }

export const getCohortOptions = () => getJson<CohortOptions>("/api/cohort/options");
export const getCohortSummary = (f: CohortFilters, signal?: AbortSignal) => getJson<CohortSummary>(`/api/cohort/summary${query(f)}`, signal);
export const getCohortStats = (f: CohortFilters, signal?: AbortSignal) => getJson<CohortStatsResponse>(`/api/cohort/stats${query(f)}`, signal);
export const getCohortPoints = (f: CohortFilters, signal?: AbortSignal) => getJson<CohortPointsResponse>(`/api/cohort/points${query(f)}`, signal);
export const getCohortSamples = (f: CohortFilters, page: SamplePage, signal?: AbortSignal) =>
  getJson<SamplesResponse>(`/api/cohort/samples${query({ ...f, ...page })}`, signal);
