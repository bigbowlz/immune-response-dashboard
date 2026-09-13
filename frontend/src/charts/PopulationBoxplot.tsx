import Plotly from "plotly.js-cartesian-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import type { Annotation, Data, Layout } from "plotly.js";
import { POPULATION_LABELS, type Population, type ResponsePoint, type ResponseStat } from "../types";

const Plot = createPlotlyComponent(Plotly);

// Colours come from the stylesheet's custom properties so the chart and the rest of the page share one palette.
function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
const FILL = { no: cssVar("--nonresponder", "#7f8ce0"), yes: cssVar("--responder", "#4caf7d") } as const;
const LINE = { no: cssVar("--nonresponder-line", "#4c5cc7"), yes: cssVar("--responder-line", "#2e7d55") } as const;
const SYMBOL = { no: "circle", yes: "diamond" } as const;
const TEXT = cssVar("--text", "#1f2328");
const ACCENT = cssVar("--accent", "#d6453d");

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
  points: ResponsePoint[];
  stats: ResponseStat[];
  alpha: number;
  sharedYMax?: number;
}

export function PopulationBoxplot({ population, points, stats, alpha, sharedYMax }: Props) {
  const own = stats.filter((r) => r.population === population).sort((a, b) => a.time_from_treatment_start - b.time_from_treatment_start);
  const days = own.map((r) => r.time_from_treatment_start);
  const categories = days.map(dayLabel);
  const hit = own.some((r) => r.significant === 1);

  const traces: Data[] = (["no", "yes"] as const).map((response) => {
    const mine = points.filter((p) => p.response === response);
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

  // p-values as annotations under each day label, so size and color are ours to set.
  // Category axes address positions by index, so use the category's index rather than its label.
  const annotations: Partial<Annotation>[] = own.map((r) => ({
    x: categories.indexOf(dayLabel(r.time_from_treatment_start)),
    xref: "x",
    y: -0.11,
    yref: "paper",
    yanchor: "top",
    text: r.p_adj < alpha ? `<b>adj. p =<br>${formatP(r.p_adj)}</b>` : `adj. p =<br>${formatP(r.p_adj)}`,
    showarrow: false,
    font: { size: 12, color: r.p_adj < alpha ? ACCENT : TEXT, family: "Inter, system-ui, sans-serif" },
    align: "center",
  }));

  const layout: Partial<Layout> = {
    title: { text: POPULATION_LABELS[population], font: { size: 14, color: TEXT }, x: 0.02, xanchor: "left" },
    boxmode: "group",
    margin: { l: 52, r: 12, t: 36, b: 110 },
    height: 380,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: TEXT },
    xaxis: { type: "category", categoryorder: "array", categoryarray: categories, showgrid: false, tickfont: { size: 12 } },
    yaxis: { title: { text: "Percent of total" }, gridcolor: "#eef0f3", zeroline: false, rangemode: "tozero", range: sharedYMax ? [0, sharedYMax] : undefined },
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
