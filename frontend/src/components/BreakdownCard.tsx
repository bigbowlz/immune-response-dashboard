import { Card } from "./Card";
import { dayLabel } from "../charts/PopulationBoxplot";
import type { BreakdownRow } from "../types";

const CATEGORY_LABELS: Record<string, string> = {
  yes: "Responder", no: "Non-responder", unknown: "No response recorded", M: "Male", F: "Female",
};

/** One composition table for the selected cohort: category, samples, subjects, share of the cohort. */
export function BreakdownCard({ title, rows, timepoint }: { title: string; rows: BreakdownRow[]; timepoint?: boolean }) {
  return (
    <Card nested title={title}>
      <table className="data">
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col" className="num">Samples</th>
            <th scope="col" className="num">Subjects</th>
            <th scope="col" className="num">% of Total (by sample)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.category)}>
              <td>{timepoint ? dayLabel(Number(r.category)) : CATEGORY_LABELS[String(r.category)] ?? String(r.category)}</td>
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
