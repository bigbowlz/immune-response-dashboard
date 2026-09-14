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
}

export function PopulationBoxplot({ population, points, stats, timepoints, alpha, sharedYMax }: Props) {
  const { FILL, LINE, TEXT, MUTED, ACCENT } = readPalette();
  const days = [...timepoints].sort((a, b) => a - b);
  const categories = days.map(dayLabel);
  const own = new Map(stats.filter((r) => r.population === population).map((r) => [r.time_from_treatment_start, r]));
  // A day whose test could not run shows no boxes at all: its samples cannot be read as a comparison.
  const testable = new Set(days.filter((d) => own.get(d)?.status === "ok"));
  const hit = days.some((d) => own.get(d)?.significant === 1);

  const traces: Data[] = (["no", "yes"] as const).map((response) => {
    const mine = points.filter((p) => p.response === response && testable.has(p.time_from_treatment_start));
    return {
      type: "box",
      name: response === "yes" ? "Responder" : "Non-responder",
      x: mine.map((p) => dayLabel(p.time_from_treatment_start)),
      y: mine.map((p) => p.percentage),
      text: mine.map((p) => `${p.sample} (${p.subject})`),
      hovertemplate: "%{text}<br>%{y:.2f}%<extra></extra>",
      boxpoints: "all",
      jitter: 0.6,
      pointpos: 0,
      marker: { color: LINE[response], size: 3.5, opacity: 0.6, symbol: SYMBOL[response] },
      line: { color: LINE[response], width: 1.2 },
      fillcolor: FILL[response] + "99",
      offsetgroup: response,
      legendgroup: response,
    } as Data;
  });

  // Adjusted p-values (or `unavailable`) as annotations under each day label, so size and colour are ours to set.
  // Category axes address positions by index, so use the category's index rather than its label.
  const annotations: Partial<Annotation>[] = days.map((day, index) => {
    const row = own.get(day);
    const available = row?.status === "ok" && row.p_adj !== null;
    const significant = available && row.p_adj! < alpha;
    return {
      x: index,
      xref: "x",
      y: -0.11,
      yref: "paper",
      yanchor: "top",
      text: !available ? "unavailable" : significant ? `<b>adj. p =<br>${formatP(row.p_adj!)}</b>` : `adj. p =<br>${formatP(row!.p_adj!)}`,
      showarrow: false,
      font: { size: 12, color: !available ? MUTED : significant ? ACCENT : TEXT, family: "Inter, system-ui, sans-serif" },
      align: "center",
    };
  });

  const layout: Partial<Layout> = {
    title: { text: POPULATION_LABELS[population], font: { size: 14, color: TEXT }, x: 0.02, xanchor: "left" },
    boxmode: "group",
    margin: { l: 52, r: 12, t: 36, b: 110 },
    height: 380,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: TEXT },
    xaxis: { type: "category", categoryorder: "array", categoryarray: categories, showgrid: false, tickfont: { size: 12 } },
    yaxis: { title: { text: "Percent of total (five populations)" }, gridcolor: "#eef0f3", zeroline: false, rangemode: "tozero", range: sharedYMax ? [0, sharedYMax] : undefined },
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
