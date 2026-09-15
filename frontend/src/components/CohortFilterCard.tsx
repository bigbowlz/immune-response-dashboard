import { useId } from "react";
import { Card } from "./Card";
import { Select } from "./Select";
import { Toggle } from "./Toggle";
import { dayLabel } from "../charts/PopulationBoxplot";
import type { CohortFilterKey, CohortFilters, CohortOptions } from "../types";

export const FILTER_LABELS: Record<CohortFilterKey, string> = {
  condition: "Condition",
  treatment: "Treatment",
  sample_type: "Sample type",
  project: "Project",
  time_from_treatment_start: "Timepoints",
};

/** The order of the selects; the crumb line follows the same order. */
const FILTER_ORDER: CohortFilterKey[] = ["condition", "treatment", "sample_type", "time_from_treatment_start", "project"];

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Display form of one filter value. Sample types and project ids keep the spelling the data uses. */
export function filterValueLabel(key: CohortFilterKey, value: string): string {
  if (value === "all") return "All";
  if (key === "time_from_treatment_start") return dayLabel(Number(value));
  if (key === "condition" || key === "treatment") return capitalise(value);
  return value;
}

interface Props {
  filters: CohortFilters;
  options: CohortOptions | null;
  onChange: (next: CohortFilters) => void;
  isDefault: boolean;
  onBaseline: (on: boolean) => void;
  onReset: () => void;
}

export function CohortFilterCard({ filters, options, onChange, isDefault, onBaseline, onReset }: Props) {
  const id = useId();
  return (
    <Card>
      <div className="filter-card">
        <p className="crumbs">
          {FILTER_ORDER.map((key, index) => (
            <span key={key}>
              {index > 0 && <span className="crumb__sep" aria-hidden="true">/</span>}
              <span className="crumb__label">{FILTER_LABELS[key]}: </span>
              <span className="crumb__value">{filterValueLabel(key, filters[key])}</span>
            </span>
          ))}
        </p>
        <div className="fields">
          {FILTER_ORDER.map((key) => (
            <fieldset className="field" key={key}>
              <legend className="field__label">{FILTER_LABELS[key]}</legend>
              <Select
                id={`${id}-${key}`}
                label={FILTER_LABELS[key]}
                value={options ? filters[key] : ""}
                disabled={!options}
                options={options ? [{ value: "all", label: "All" }, ...options[key].map((v) => ({ value: String(v), label: filterValueLabel(key, String(v)) }))] : []}
                onChange={(value) => onChange({ ...filters, [key]: value })}
              />
            </fieldset>
          ))}
          <div className="toggles">
            <Toggle label="Baseline only" checked={filters.time_from_treatment_start === "0"} disabled={!options} onChange={onBaseline} />
            <Toggle label="Default cohort" checked={isDefault} disabled={!options} onChange={(on) => { if (on) onReset(); }} />
          </div>
        </div>
      </div>
    </Card>
  );
}
