import Plotly from "plotly.js-cartesian-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import type { Annotation, Data, Layout } from "plotly.js";
import { POPULATION_LABELS, type CohortPoint, type CohortStat, type Population } from "../types";

const Plot = createPlotlyComponent(Plotly);

// Colours come from the stylesheet's custom properties so the chart and the rest of the page share one palette.
function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
// Resolved at render time, not at module load, so the stylesheet is guaranteed to be applied first.
function readPalette() {
  return {
    FILL: { no: cssVar("--nonresponder", "#7f8ce0"), yes: cssVar("--responder", "#4caf7d") } as const,
    LINE: { no: cssVar("--nonresponder-line", "#4c5cc7"), yes: cssVar("--responder-line", "#2e7d55") } as const,
    TEXT: cssVar("--text", "#1f2328"),
    MUTED: cssVar("--muted", "#5f6672"),
    ACCENT: cssVar("--accent", "#d6453d"),
  };
}
const SYMBOL = { no: "circle", yes: "diamond" } as const;

export function formatP(p: number): string {
  if (p < 0.001) return "< 0.001";
  return p.toFixed(3);
}

export function formatDelta(d: number): string {
  return (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(2);
}

export const dayLabel = (day: number) => (day === 0 ? "Day 0 (baseline)" : `Day ${day}`);

interface Props {
  population: Population;
  points: CohortPoint[];
  stats: CohortStat[];
  /** The selected timepoints, in the order they appear on the x-axis. */
  timepoints: number[];
  alpha: number;
  sharedYMax?: number;
  /** When true (cohorts with more than 3,000 samples carrying a response), plot only the outliers
   * instead of every individual point, so the chart stays legible and light to render. */
  outliersOnly?: boolean;
}

export function PopulationBoxplot({ population, points, stats, timepoints, alpha, sharedYMax, outliersOnly }: Props) {
  const { FILL, LINE, TEXT, MUTED, ACCENT } = readPalette();
  const days = [...timepoints].sort((a, b) => a - b);
  const categories = days.map(dayLabel);
  const own = new Map(stats.filter((r) => r.population === population).map((r) => [r.time_from_treatment_start, r]));
  // A day whose test could not run shows no boxes at all: its samples cannot be read as a comparison.
  const testable = new Set(days.filter((d) => own.get(d)?.status === "ok"));
  const hit = days.some((d) => own.get(d)?.significant === 1);

  // Boxes and points are separate traces on a numeric axis: the box is hover-only for its statistics
  // (max, upper fence, q3, median, q1, lower fence, min, each label pointing at its line), the points carry
  // the sample details. Inside the box body the box wins the hover; elsewhere the nearest point does.
  const OFFSET = { no: -0.2, yes: 0.2 } as const;
  const jitter = (sample: string) => {
    let h = 0;
    for (const ch of sample) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return ((h % 1000) / 1000 - 0.5) * 0.2;
  };
  const traces: Data[] = (["no", "yes"] as const).flatMap((response) => {
    const mine = points.filter((p) => p.response === response && testable.has(p.time_from_treatment_start));
    const name = response === "yes" ? "Responder" : "Non-responder";
    const box = {
      type: "box",
      name,
      x: mine.map((p) => days.indexOf(p.time_from_treatment_start) + OFFSET[response]),
      y: mine.map((p) => p.percentage),
      width: 0.3,
      // Outliers stay enabled so the hover reports the fences as well as min/max; the markers themselves are
      // invisible whenever the scatter layer draws every point.
      boxpoints: "outliers",
      hoveron: "boxes",
      hoverinfo: "y",
      marker: { color: LINE[response], size: 3.5, opacity: outliersOnly ? 0.6 : 0, symbol: SYMBOL[response] },
      line: { color: LINE[response], width: 1.2 },
      fillcolor: FILL[response] + "99",
      legendgroup: response,
    } as Data;
    if (outliersOnly) return [box];
    // Points inside a box body do not answer hover, so the box can report its statistics there; points
    // outside it (whiskers and beyond) carry the sample details. The split uses the same linear
    // quartiles Plotly draws, purely to decide which points stay hoverable.
    const inBody = new Set<CohortPoint>();
    for (const day of days) {
      const values = mine.filter((p) => p.time_from_treatment_start === day).map((p) => p.percentage).sort((a, b) => a - b);
      if (values.length === 0) continue;
      const q = (f: number) => { const i = (values.length - 1) * f; const lo = Math.floor(i); return values[lo] + (values[Math.min(lo + 1, values.length - 1)] - values[lo]) * (i - lo); };
      const [q1, q3] = [q(0.25), q(0.75)];
      for (const p of mine) if (p.time_from_treatment_start === day && p.percentage >= q1 && p.percentage <= q3) inBody.add(p);
    }
    const dots = (subset: CohortPoint[], hoverable: boolean) => ({
      type: "scatter",
      mode: "markers",
      name,
      x: subset.map((p) => days.indexOf(p.time_from_treatment_start) + OFFSET[response] + jitter(p.sample)),
      y: subset.map((p) => p.percentage),
      text: subset.map((p) => [
        `Count: ${p.count.toLocaleString()} / ${p.total_count.toLocaleString()}`,
        `Population: ${POPULATION_LABELS[population]}`,
        `Sample: ${p.sample}`,
        `Subject: ${p.subject}`,
        `Response: ${name}`,
      ].join("<br>")),
      hoverinfo: hoverable ? "y+text" : "skip",
      marker: { color: LINE[response], size: 3.5, opacity: 0.6, symbol: SYMBOL[response] },
      legendgroup: response,
      showlegend: false,
    }) as Data;
    return [box, dots(mine.filter((p) => inBody.has(p)), false), dots(mine.filter((p) => !inBody.has(p)), true)];
  });

  // Adjusted p-values (or `unavailable`) as annotations under each day label, so size and colour are ours to set.
  // Category axes address positions by index, so use the category's index rather than its label.
  const annotations: Partial<Annotation>[] = days.map((day, index) => {
    const row = own.get(day);
    const adjusted = row?.status === "ok" ? row.p_adj : null;
    const significant = adjusted !== null && adjusted < alpha;
    const text = adjusted === null ? "unavailable" : `adj. p =<br>${formatP(adjusted)}`;
    return {
      x: index,
      xref: "x",
      y: -0.11,
      yref: "paper",
      yanchor: "top",
      text: significant ? `<b>${text}</b>` : text,
      showarrow: false,
      font: { size: 12, color: adjusted === null ? MUTED : significant ? ACCENT : TEXT, family: "Inter, system-ui, sans-serif" },
      align: "center",
    };
  });

  const layout: Partial<Layout> = {
    title: { text: POPULATION_LABELS[population], font: { size: 14, color: TEXT }, x: 0.02, xanchor: "left" },
    hovermode: "closest",
    // Plotly ranks a box just under the hover limit so any nearby point beats it; a small limit means a point
    // wins only when the cursor is on its marker and the box reports its statistics everywhere else in its span.
    hoverdistance: 6,
    margin: { l: 52, r: 12, t: 36, b: 110 },
    height: 380,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: TEXT },
    xaxis: { tickvals: days.map((_, i) => i), ticktext: categories, range: [-0.5, days.length - 0.5], showgrid: false, zeroline: false, fixedrange: true, tickfont: { size: 12, color: TEXT } },
    yaxis: { title: { text: "Cell frequency (%)", font: { size: 12, color: TEXT }, standoff: 8 }, tickfont: { size: 12, color: TEXT }, hoverformat: ".2f", gridcolor: "#eef0f3", zeroline: false, rangemode: "tozero", range: sharedYMax ? [0, sharedYMax] : undefined },
    legend: { orientation: "h", y: -0.4, x: 0.5, xanchor: "center" },
    annotations,
    showlegend: true,
  };

  return (
    <div className={`chart-panel${hit ? " chart-panel--hit" : ""}`} role="img" aria-label={`${POPULATION_LABELS[population]} percent of total by day, responders versus non-responders`}>
      <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }} style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
