import { useEffect, useState } from "react";
import { getSubsetOptions, getSubsets } from "../api";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import type { BreakdownRow, FilterKey, SubsetFilters, SubsetOptions, SubsetsResponse } from "../types";

const DEFAULTS: SubsetFilters = { condition: "melanoma", treatment: "miraclib", sample_type: "PBMC", time_from_treatment_start: "0" };
const FILTER_LABELS: Record<FilterKey, string> = {
  condition: "Condition", treatment: "Treatment", sample_type: "Sample type", time_from_treatment_start: "Timepoint (days)",
};
const CATEGORY_LABELS: Record<string, string> = { yes: "Responder", no: "Non-responder", unknown: "No response recorded", M: "Male", F: "Female" };

function BreakdownCard({ title, rows, timepoint }: { title: string; rows: BreakdownRow[]; timepoint?: boolean }) {
  return (
    <Card nested title={title}>
      <table className="data">
        <thead>
          <tr><th scope="col">Category</th><th scope="col" className="num">Samples</th><th scope="col" className="num">Subjects</th><th scope="col" className="num">% of Total (by sample)</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.category)}>
              <td>{timepoint ? `Day ${r.category}` : CATEGORY_LABELS[String(r.category)] ?? String(r.category)}</td>
              <td className="num">{r.n_samples.toLocaleString()}</td>
              <td className="num">{r.n_subjects.toLocaleString()}</td>
              <td className="num">{r.pct_samples.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function SubsetsPage() {
  const [options, setOptions] = useState<SubsetOptions | null>(null);
  const [filters, setFilters] = useState<SubsetFilters>(DEFAULTS);
  const [data, setData] = useState<SubsetsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSubsetOptions().then(setOptions).catch((e: Error) => setError(e.message));
  }, []);

  // One request per filter change; an older response can never overwrite a newer one.
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getSubsets(filters, controller.signal)
      .then((d) => { setData(d); setError(null); })
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filters]);

  const isDefault = (Object.keys(DEFAULTS) as FilterKey[]).every((k) => filters[k] === DEFAULTS[k]);
  const summary = Object.entries(filters)
    .map(([k, v]) => `${FILTER_LABELS[k as FilterKey]}: ${v === "all" ? "all" : k === "time_from_treatment_start" ? `day ${v}` : v}`)
    .join(" / ");

  return (
    <>
      <PageHeader title="Cohort subsets" subtitle="Melanoma PBMC samples at baseline from patients treated with miraclib, broken down by project, response and sex. Widen or narrow the subset with the filters." />
      <Card
        title="Key metadata distribution"
        subtitle={summary}
        actions={<button className="button" onClick={() => setFilters(DEFAULTS)} disabled={isDefault}>Reset to baseline cohort</button>}
      >
        <div className="toolbar">
          {(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => (
            <label key={key}>
              {FILTER_LABELS[key]}
              <select value={filters[key]} onChange={(e) => setFilters({ ...filters, [key]: e.target.value })} disabled={!options}>
                <option value="all">All</option>
                {(options?.[key] ?? []).map((v) => <option key={String(v)} value={String(v)}>{String(v)}</option>)}
              </select>
            </label>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
        {loading && !data && <p className="note" aria-live="polite">Counting samples…</p>}
        {data && data.n_samples === 0 && (
          <div className="empty" aria-live="polite">
            <span>No samples match these filters.</span>
            <button className="button" onClick={() => setFilters(DEFAULTS)}>Reset to baseline cohort</button>
          </div>
        )}
        {data && data.n_samples > 0 && (
          <div className={loading ? "refreshable refreshable--busy" : "refreshable"} aria-busy={loading}>
            <p className="headline"><span className="metric">{data.n_samples.toLocaleString()}</span> samples from <span className="metric">{data.n_subjects.toLocaleString()}</span> subjects</p>
            <div className="grid">
              <BreakdownCard title="Project" rows={data.breakdowns.project} />
              <BreakdownCard title="Response" rows={data.breakdowns.response} />
              <BreakdownCard title="Sex" rows={data.breakdowns.sex} />
              {filters.time_from_treatment_start === "all" && <BreakdownCard title="Timepoint" rows={data.breakdowns.time_from_treatment_start} timepoint />}
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
