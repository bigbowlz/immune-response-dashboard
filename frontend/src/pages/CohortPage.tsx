import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getCohortOptions, getCohortPoints, getCohortSamples, getCohortStats, getCohortSummary } from "../api";
import { PopulationBoxplot, dayLabel, formatDelta, formatP } from "../charts/PopulationBoxplot";
import { BreakdownCard } from "../components/BreakdownCard";
import { Card } from "../components/Card";
import { Chip } from "../components/Chip";
import { CohortFilterCard } from "../components/CohortFilterCard";
import { DataTable, type ColumnDef, type SortDir } from "../components/DataTable";
import { PageHeader } from "../components/PageHeader";
import {
  POPULATIONS, POPULATION_LABELS,
  type CohortFilters, type CohortOptions, type CohortPoint, type CohortStat, type CohortStatsResponse,
  type CohortSummary, type Population, type SampleColumn, type SampleRow,
} from "../types";

// The option lists never change for a given database; keep them across page switches so the selects never render empty twice.
let optionsCache: CohortOptions | null = null;

const DEFAULT_FILTERS: CohortFilters = {
  condition: "melanoma", treatment: "miraclib", sample_type: "PBMC", project: "all", time_from_treatment_start: "all",
};
const PAGE_SIZE = 50;
interface TableState { sort: SampleColumn; dir: SortDir; page: number }
const DEFAULT_TABLE: TableState = { sort: "sample", dir: "asc", page: 0 };

const populationLabel = (s: CohortStat) => POPULATION_LABELS[s.population];
const direction = (delta: number) => (delta >= 0 ? "higher" : "lower");

/** One sentence that holds whether or not anything is significant, and names the reason when nothing ran. */
function headline(rows: CohortStat[], alpha: number): ReactNode {
  const ok = rows.filter((r) => r.status === "ok" && r.effect_size !== null && r.p_adj !== null);
  if (ok.length === 0) {
    const reason = rows.find((r) => r.reason)?.reason ?? "no comparable samples";
    return <>No response comparison is available for this cohort: {reason}.</>;
  }
  const earliest = Math.min(...ok.map((r) => r.time_from_treatment_start));
  const ranked = ok
    .filter((r) => r.time_from_treatment_start === earliest)
    .sort((a, b) => Math.abs(b.effect_size!) - Math.abs(a.effect_size!));
  const top = ranked[0];
  const hits = ok.filter((r) => r.significant === 1).sort((a, b) => Math.abs(b.effect_size!) - Math.abs(a.effect_size!));
  return (
    <>
      At {dayLabel(earliest).toLowerCase()}, the largest difference between responders and non-responders is{" "}
      <strong>{populationLabel(top)}</strong> ({direction(top.effect_size!)} in responders, Cliff's delta {formatDelta(top.effect_size!)}, adjusted p {formatP(top.p_adj!)}).{" "}
      {hits.length === 0
        ? <>No test in this cohort has an adjusted p below {alpha}.</>
        : <>{hits.length === 1 ? "One test" : `${hits.length} tests`} in this cohort {hits.length === 1 ? "has" : "have"} an adjusted p below {alpha}: {hits.map((r) => `${populationLabel(r)} at ${dayLabel(r.time_from_treatment_start).toLowerCase()}`).join(", ")}.</>}
    </>
  );
}


const STAT_COLUMNS = (alpha: number): ColumnDef<CohortStat>[] => [
  { key: "population", label: "Population", format: (v) => POPULATION_LABELS[v as Population] },
  { key: "time_from_treatment_start", label: "Day", numeric: true },
  { key: "n_responders", label: "n resp.", numeric: true, format: (v) => Number(v).toLocaleString() },
  { key: "n_nonresponders", label: "n non-resp.", numeric: true, format: (v) => Number(v).toLocaleString() },
  { key: "median_responders", label: "Median resp. (%)", numeric: true, format: (v) => (v === null ? "—" : Number(v).toFixed(2)) },
  { key: "median_nonresponders", label: "Median non-resp. (%)", numeric: true, format: (v) => (v === null ? "—" : Number(v).toFixed(2)) },
  { key: "u_statistic", label: "U", numeric: true, help: "Two-sided Mann-Whitney U test per population per selected timepoint, responders against non-responders.", format: (v) => (v === null ? "—" : Number(v).toLocaleString()) },
  // An unavailable cell has no p-values: the reason takes their place.
  { key: "p_raw", label: "p (raw)", numeric: true, render: (v, row) => (row.status === "ok" && v !== null ? formatP(Number(v)) : <span className="reason">{row.reason}</span>) },
  { key: "p_adj", label: "p (BH-adjusted)", numeric: true, render: (v, row) => (row.status === "ok" && v !== null ? <span className={Number(v) < alpha ? "sig" : undefined}>{formatP(Number(v))}</span> : "—") },
  { key: "effect_size", label: "Cliff's delta", numeric: true, help: "Positive when responders have the higher frequency.", format: (v) => (v === null ? "—" : formatDelta(Number(v))) },
  {
    key: "status",
    label: "Status",
    render: (_v, row) =>
      row.status === "unavailable"
        ? <Chip tone="neutral">Unavailable</Chip>
        : <Chip tone={row.significant === 1 ? "green" : "neutral"}>{row.significant === 1 ? "Significant" : "n.s."}</Chip>,
  },
];

const SAMPLE_COLUMNS: ColumnDef<SampleRow>[] = [
  { key: "sample", label: "Sample ID" },
  { key: "subject", label: "Subject ID" },
  { key: "project", label: "Project" },
  { key: "condition", label: "Condition" },
  { key: "treatment", label: "Treatment" },
  { key: "sample_type", label: "Sample type" },
  { key: "time_from_treatment_start", label: "Timepoint (days)", numeric: true },
  // The CSV keeps the empty field the database holds; the table spells it out.
  { key: "response", label: "Response", format: (v) => (v === null ? "not recorded" : String(v)) },
  { key: "sex", label: "Sex" },
];

export function CohortPage() {
  const [options, setOptions] = useState<CohortOptions | null>(optionsCache);
  const [filters, setFilters] = useState<CohortFilters>(DEFAULT_FILTERS);

  const [summary, setSummary] = useState<CohortSummary | null>(null);
  const [stats, setStats] = useState<CohortStatsResponse | null>(null);
  const [points, setPoints] = useState<CohortPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [table, setTable] = useState<TableState>(DEFAULT_TABLE);
  const [samples, setSamples] = useState<SampleRow[]>([]);
  const [samplesTotal, setSamplesTotal] = useState(0);
  const [samplesLoading, setSamplesLoading] = useState(true);
  // The cohort fetch below already loads the first samples page, so the samples-only effect stands
  // down for the render that follows a filter change (and for the first render).
  const samplesHandled = useRef(true);
  // Both effects fetch the samples list, so one counter decides which answer may be rendered: a
  // request writes the list only while it is still the newest one, whichever effect started it.
  const samplesRequest = useRef(0);
  const lastSamples = useRef<{ controller: AbortController; shared: boolean } | null>(null);
  // The same idea for the cohort fetch as a whole: a superseded filter fetch may not report its failure.
  const filterRequest = useRef(0);

  /**
   * Start a samples fetch and commit it only if it is still the newest one. `shared` marks the fetch
   * that rides along with a filter change: it supersedes an in-flight sort/page fetch, while a
   * sort/page fetch never aborts a filter fetch (whose summary, stats and points share its controller).
   */
  const startSamples = (f: CohortFilters, t: TableState, controller: AbortController, shared: boolean) => {
    const previous = lastSamples.current;
    if (previous && previous.controller !== controller && (shared || !previous.shared)) previous.controller.abort();
    lastSamples.current = { controller, shared };
    const id = ++samplesRequest.current;
    setSamplesLoading(true);
    const request = getCohortSamples(f, { sort: t.sort, dir: t.dir, limit: PAGE_SIZE, offset: t.page * PAGE_SIZE }, controller.signal);
    request.then(
      (r) => {
        if (id !== samplesRequest.current) return;
        setSamples(r.rows); setSamplesTotal(r.total); setSamplesLoading(false);
        // A fetch that rides along with a filter change must not clear the page-level error: the
        // filter effect below owns that state, and a samples success that resolves after a filter
        // failure has already reported it must not wipe the error back to null.
        if (!shared) setError(null);
      },
      () => {
        if (id === samplesRequest.current && !controller.signal.aborted) setSamplesLoading(false);
      },
    );
    return request;
  };

  useEffect(() => {
    if (optionsCache) return;
    getCohortOptions().then((o) => { optionsCache = o; setOptions(o); }).catch((e: Error) => setError(e.message));
  }, []);

  // One controller per filter change covering summary, stats, points and the first samples page:
  // a superseded response is aborted and never reaches the state.
  useEffect(() => {
    const controller = new AbortController();
    const filterId = ++filterRequest.current;
    setLoading(true);
    const samplesPromise = startSamples(filters, DEFAULT_TABLE, controller, true);
    const samplesId = samplesRequest.current;
    Promise.all([
      getCohortSummary(filters, controller.signal),
      getCohortStats(filters, controller.signal),
      getCohortPoints(filters, controller.signal),
      samplesPromise,
    ])
      .then(([s, st, p]) => {
        if (controller.signal.aborted || filterId !== filterRequest.current) return;
        setSummary(s); setStats(st); setPoints(p.points);
        setError(null);
      })
      .catch((e: Error) => {
        if (e.name === "AbortError") return;
        // Failures obey the same guards as successes: a newer samples fetch keeps its rows, and a
        // superseded filter fetch reports nothing at all.
        if (samplesId === samplesRequest.current) { setSamples([]); setSamplesTotal(0); setSamplesLoading(false); }
        if (filterId !== filterRequest.current) return;
        setSummary(null); setStats(null); setPoints([]);
        setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted && filterId === filterRequest.current) setLoading(false);
      });
    return () => controller.abort();
  }, [filters]);

  // Sorting and paging re-fetch the samples list alone, under their own controller.
  useEffect(() => {
    if (samplesHandled.current) { samplesHandled.current = false; return; }
    const controller = new AbortController();
    startSamples(filters, table, controller, false)
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [filters, table]);

  // "Default cohort" is an explicit switch: on resets every selector, off leaves them as they are, and any
  // selector change switches it off. It never switches itself on.
  const [defaultOn, setDefaultOn] = useState(true);
  const applyFilters = (next: CohortFilters) => {
    samplesHandled.current = true;
    setTable(DEFAULT_TABLE);
    setFilters(next);
    if ((Object.keys(DEFAULT_FILTERS) as Array<keyof CohortFilters>).some((k) => next[k] !== filters[k])) setDefaultOn(false);
  };

  const rows = stats?.rows ?? [];
  const days = useMemo(() => [...new Set(rows.map((r) => r.time_from_treatment_start))].sort((a, b) => a - b), [rows]);
  const byPopulation = useMemo(() => {
    const map = new Map<Population, CohortPoint[]>();
    for (const p of points) map.set(p.population, [...(map.get(p.population) ?? []), p]);
    return map;
  }, [points]);
  const alpha = stats?.alpha ?? 0.05;
  // Plotly renders every individual point by default; past a few thousand that gets slow and cluttered,
  // so wide cohorts fall back to outliers only. Based on samples with a recorded response (what the
  // boxplots actually draw), not the raw sample count.
  const wideCohort = stats !== null && stats.n_samples - stats.n_missing_response > 3000;
  const nUnavailable = rows.filter((r) => r.status === "unavailable").length;
  const empty = !loading && summary !== null && summary.n_samples === 0;
  // The cohort fetch failed and left nothing to draw: say so instead of leaving skeletons up.
  const failed = !loading && error !== null && summary === null;

  // Defined once: the samples list is also worth showing when the rest of the cohort fetch failed but a
  // newer samples request had already delivered rows for these filters.
  const samplesCard = (
    <Card title="Matching samples">
      {/* The failed card above already shows the page-level error once; do not repeat it here. */}
      {!failed && error && <p className="error">{error}</p>}
      <div className="samples">
      <DataTable
        columns={SAMPLE_COLUMNS}
        rows={samples}
        pageSize={PAGE_SIZE}
        total={samplesTotal}
        page={table.page}
        onPageChange={(page) => setTable((t) => ({ ...t, page }))}
        sortKey={table.sort}
        sortDir={table.dir}
        onSortChange={(key, dir) => setTable({ sort: key as SampleColumn, dir, page: 0 })}
        loading={samplesLoading}
        emptyText="No samples match these filters."
        rowKey={(row) => row.sample}
      />
      </div>
    </Card>
  );

  return (
    <>
      <PageHeader
        title="Cohort analysis"
        subtitle="Explore immune cell frequencies and compare treatment response within a selected cohort."
      />
      <CohortFilterCard
        filters={filters}
        options={options}
        onChange={applyFilters}
        defaultOn={defaultOn}
        onBaseline={(on) => applyFilters({ ...filters, time_from_treatment_start: on ? "0" : "all" })}
        onDefault={(on) => { if (on) { applyFilters(DEFAULT_FILTERS); setDefaultOn(true); } else setDefaultOn(false); }}
      />

      {failed ? (
        <>
          <Card title="This cohort could not be loaded">
            <p className="error">{error}</p>
            <p className="note">Change a filter to try another cohort, or reset to the default one.</p>
          </Card>
          {samples.length > 0 && samplesCard}
        </>
      ) : empty ? (
        <Card title="Key metadata distribution">
          <div className="empty" aria-live="polite">
            <span>No samples match these filters.</span>
            <button type="button" className="button" onClick={() => applyFilters(DEFAULT_FILTERS)}>Reset to default cohort</button>
          </div>
        </Card>
      ) : (
        <>
          <Card title="Key metadata distribution">
            {loading || !summary ? (
              <div className="skeleton skeleton--block" aria-hidden="true" />
            ) : (
              <>
                <p className="headline">
                  <span className="metric">{summary.n_samples.toLocaleString()}</span> samples from <span className="metric">{summary.n_subjects.toLocaleString()}</span> subjects
                </p>
                <div className="grid">
                  <BreakdownCard title="Project" rows={summary.breakdowns.project} />
                  <BreakdownCard title="Response" rows={summary.breakdowns.response} />
                  <BreakdownCard title="Sex" rows={summary.breakdowns.sex} />
                </div>
              </>
            )}
          </Card>

          <Card
            title="Population frequencies by response"
          >
            {loading || !stats ? (
              <div className="charts">
                {POPULATIONS.map((population) => <div key={population} className="skeleton" aria-hidden="true" />)}
              </div>
            ) : (
              <>
                <p className="result">{headline(rows, alpha)}</p>
                {wideCohort && (
                  <p className="note">
                    Individual points are hidden for cohorts with more than 3,000 samples; boxes and whiskers show the distribution.
                  </p>
                )}
                <div className="charts">
                  {POPULATIONS.map((population) => {
                    const own = rows.filter((r) => r.population === population);
                    const usable = own.filter((r) => r.status === "ok");
                    if (usable.length === 0) {
                      return (
                        <div key={population} className="chart-panel chart-panel--empty">
                          <h3 className="chart-panel__title">{POPULATION_LABELS[population]}</h3>
                          <p className="note">No comparison at the selected timepoints: {own.find((r) => r.reason)?.reason ?? "no comparable samples"}.</p>
                        </div>
                      );
                    }
                    return (
                      <PopulationBoxplot
                        key={population}
                        population={population}
                        points={byPopulation.get(population) ?? []}
                        stats={rows}
                        timepoints={days}
                        alpha={alpha}
                        outliersOnly={wideCohort}
                      />
                    );
                  })}
                </div>
                {summary && summary.n_missing_response > 0 && (
                  <p className="note">
                    {summary.n_missing_response.toLocaleString()} of {summary.n_samples.toLocaleString()} matching samples are excluded from the comparison because no response is recorded for their subject.
                  </p>
                )}
              </>
            )}
          </Card>

          <Card
            title="Statistics"
          >
            <div className="stats">
            <DataTable
              columns={STAT_COLUMNS(alpha)}
              rows={rows}
              pageSize={rows.length || 15}
              loading={loading}
              emptyText="No statistics for this cohort."
              rowKey={(row) => `${row.population}-${row.time_from_treatment_start}`}
            />
            </div>
            {stats && (
              <p className="note" style={{ marginTop: 10 }}>
                Benjamini–Hochberg across the {stats.n_tests.toLocaleString()} valid {stats.n_tests === 1 ? "test" : "tests"} in this cohort ({nUnavailable.toLocaleString()} unavailable). Significant means adjusted p below {alpha}.
              </p>
            )}
          </Card>

          {samplesCard}
        </>
      )}
    </>
  );
}
