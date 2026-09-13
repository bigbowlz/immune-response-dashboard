import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getResponseSamples, getResponseStats } from "../api";
import { PopulationBoxplot, formatDelta, formatP } from "../charts/PopulationBoxplot";
import { Card } from "../components/Card";
import { Chip } from "../components/Chip";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageHeader } from "../components/PageHeader";
import { POPULATIONS, POPULATION_LABELS, type ResponsePoint, type ResponseStat } from "../types";

const label = (s: ResponseStat) => POPULATION_LABELS[s.population];
const direction = (s: ResponseStat) => (s.effect_size >= 0 ? "higher" : "lower");

/** One sentence that is true whether or not anything is significant. Ranks by effect size, never hides a null. */
function headline(stats: ResponseStat[], alpha: number): { text: ReactNode; hits: ResponseStat[] } {
  const baseline = stats.filter((s) => s.time_from_treatment_start === 0);
  const hits = baseline.filter((s) => s.significant === 1).sort((a, b) => Math.abs(b.effect_size) - Math.abs(a.effect_size));
  if (hits.length > 0) {
    const top = hits[0];
    return {
      hits,
      text: (
        <>
          <strong>{label(top)}</strong> {direction(top)} in responders at baseline (Cliff's delta {formatDelta(top.effect_size)}, adjusted p {formatP(top.p_adj)})
          {hits.length > 1 && <>; also {hits.slice(1).map(label).join(", ")}</>}.
        </>
      ),
    };
  }
  const largest = [...baseline].sort((a, b) => Math.abs(b.effect_size) - Math.abs(a.effect_size))[0];
  return {
    hits,
    text: largest ? (
      <>
        No baseline population separates responders from non-responders after correction. The largest baseline difference is{" "}
        {label(largest)} ({direction(largest)} in responders, Cliff's delta {formatDelta(largest.effect_size)}, adjusted p {formatP(largest.p_adj)}); every baseline effect is small (|delta| below {Math.ceil(Math.abs(largest.effect_size) * 100) / 100}). Significance threshold: adjusted p below {alpha}.
      </>
    ) : <>No statistics available.</>,
  };
}

export function ResponsePage() {
  const [project, setProject] = useState("all");
  const [projects, setProjects] = useState<string[]>([]);
  const [stats, setStats] = useState<ResponseStat[]>([]);
  const [alpha, setAlpha] = useState(0.05);
  const [points, setPoints] = useState<ResponsePoint[]>([]);
  const [sharedY, setSharedY] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refetch both the statistics and the points when the project stratum changes; abort stale requests.
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    Promise.all([getResponseStats(project, controller.signal), getResponseSamples(project, controller.signal)])
      .then(([s, p]) => { setStats(s.rows); setAlpha(s.alpha); setProjects(s.projects); setPoints(p.points); setError(null); })
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [project]);

  const projectLabel = project === "all" ? "all projects" : `project ${project}`;

  const byPopulation = useMemo(() => {
    const map = new Map<string, ResponsePoint[]>();
    for (const p of points) map.set(p.population, [...(map.get(p.population) ?? []), p]);
    return map;
  }, [points]);
  const yMax = useMemo(() => Math.ceil(Math.max(0, ...points.map((p) => p.percentage)) / 5) * 5, [points]);

  const { text: headlineText } = useMemo(() => headline(stats, alpha), [stats, alpha]);
  const suggestive = useMemo(
    () => stats.filter((s) => s.time_from_treatment_start !== 0).sort((a, b) => a.p_adj - b.p_adj).slice(0, 2),
    [stats],
  );
  const laterHits = stats.filter((s) => s.time_from_treatment_start !== 0 && s.significant === 1);
  const nResp = stats[0]?.n_responders;
  const nNon = stats[0]?.n_nonresponders;

  const columns: ColumnDef<ResponseStat>[] = [
    { key: "population", label: "Population", format: (v) => POPULATION_LABELS[v as ResponseStat["population"]] },
    { key: "time_from_treatment_start", label: "Day", numeric: true },
    { key: "n_responders", label: "n resp.", numeric: true },
    { key: "n_nonresponders", label: "n non-resp.", numeric: true },
    { key: "median_responders", label: "Median resp. (%)", numeric: true, format: (v) => Number(v).toFixed(2) },
    { key: "median_nonresponders", label: "Median non-resp. (%)", numeric: true, format: (v) => Number(v).toFixed(2) },
    { key: "u_statistic", label: "U", numeric: true, format: (v) => Number(v).toLocaleString() },
    { key: "p_raw", label: "p (raw)", numeric: true, format: (v) => formatP(Number(v)) },
    { key: "p_adj", label: "p (BH-adjusted)", numeric: true, format: (v) => formatP(Number(v)) },
    { key: "effect_size", label: "Cliff's delta", numeric: true, format: (v) => formatDelta(Number(v)) },
    { key: "significant", label: "Significant", render: (v) => <Chip tone={v === 1 ? "green" : "neutral"}>{v === 1 ? "Significant" : "n.s."}</Chip> },
  ];

  return (
    <>
      <PageHeader
        title="Responder comparison"
        subtitle="Identify immune cell features that separate responders and non-responders among melanoma patients treated with miraclib (PBMC samples)."
      />
      {error && <Card><p className="error">{error}</p></Card>}

      <Card
        title="Baseline result (day 0)"
        subtitle={`Only baseline samples can predict response. Day 7 and day 14 differences are early treatment effects, reported below. Showing ${projectLabel}.`}
        actions={
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
            Project
            <select value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project stratum" disabled={projects.length === 0}>
              <option value="all">All projects</option>
              {projects.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        }
      >
        {loading ? <p className="note" aria-live="polite">Loading statistics…</p> : <p className="result">{headlineText}</p>}
        {!loading && suggestive.length > 0 && (
          <p className="note">
            Early treatment effects (day 7 and 14):{" "}
            {laterHits.length > 0
              ? `${laterHits.map((s) => `${label(s)} ${direction(s)} in responders at day ${s.time_from_treatment_start} (adjusted p ${formatP(s.p_adj)})`).join("; ")}.`
              : `none reaches significance; the smallest adjusted p-values are ${suggestive.map((s) => `${label(s)} ${direction(s)} in responders at day ${s.time_from_treatment_start} (adjusted p ${formatP(s.p_adj)}, delta ${formatDelta(s.effect_size)})`).join(" and ")}.`}
          </p>
        )}
      </Card>

      <Card
        title="Population frequencies by response"
        subtitle="Boxes: non-responder (blue, circles) and responder (green, diamonds) at each timepoint; points are individual samples; adjusted p under each day."
        actions={
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }} title="For comparing panels; each population has its own natural range">
            <input type="checkbox" checked={sharedY} onChange={(e) => setSharedY(e.target.checked)} /> Same Y-axis across plots
          </label>
        }
      >
        <div className="charts">
          {POPULATIONS.map((population) =>
            loading ? (
              <div key={population} className="skeleton" aria-hidden="true" />
            ) : (
              <PopulationBoxplot
                key={population}
                population={population}
                points={byPopulation.get(population) ?? []}
                stats={stats}
                alpha={alpha}
                sharedYMax={sharedY ? yMax : undefined}
              />
            ),
          )}
        </div>
        <p className="note" style={{ marginTop: 12 }}>
          {nResp !== undefined && `${nResp} responders vs ${nNon} non-responders at each timepoint (${projectLabel}). `}
          Mann-Whitney U per population per timepoint (15 tests), Benjamini-Hochberg adjusted across the 15 tests of the selected project stratum; significant means adjusted p below {alpha}.
          Each subject contributes exactly one sample per timepoint, so the samples within a test are independent; pooling the three timepoints would count each person three times.
          {project === "all" && projects.length > 1 && " Use the project selector to check that the picture holds within each project."}
        </p>
      </Card>

      <Card title="Statistics" subtitle={`One test per population per timepoint, ${projectLabel}. Cliff's delta is positive when responders have the higher frequency.`}>
        <DataTable columns={columns} rows={stats} pageSize={15} loading={loading} emptyText="No statistics. Run make pipeline, then reload." />
      </Card>
    </>
  );
}
