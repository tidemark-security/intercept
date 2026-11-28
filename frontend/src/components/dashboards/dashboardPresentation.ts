import type { DashboardMeasure } from "@/types/generated/models/DashboardMeasure";
import type { DashboardWidget } from "@/types/generated/models/DashboardWidget";

export const FIELD_LABELS: Record<string, string> = {
  human_id: "Record ID",
  picerl_stage: "PICERL stage",
  created_at: "Created",
  completed_at: "Recorded completion",
  elapsed_seconds: "Elapsed time",
  target_seconds: "Target",
  due_date: "Due date",
};

export const DISPLAY_LABELS = {
  number: "Number",
  trend: "Trend",
  breakdown: "Breakdown",
  table: "Table",
};

export const DATE_BASIS: Record<DashboardMeasure["date_basis"], string> = {
  current: "As of now",
  created_at: "By creation date",
  closed_at: "By recorded closure date",
  triaged_at: "By recorded triage date",
};

export function fieldLabel(field: string) {
  return FIELD_LABELS[field] ?? field.charAt(0).toUpperCase() + field.slice(1);
}

export function metricValue(value?: number | null, unit: DashboardMeasure["unit"] = "count") {
  if (value == null) return "—";
  if (unit === "percent") return new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(value / 100);
  if (unit === "count") return value.toLocaleString();
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = Math.round(value / 60);
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h${remainder ? ` ${remainder}m` : ""}` : `${minutes}m`;
}

export function widgetDefaults(measure: DashboardMeasure): Pick<DashboardWidget, "measure" | "title" | "display" | "parameters"> {
  return {
    measure: measure.id,
    title: measure.label,
    display: "number",
    parameters: measure.parameters.includes("target_minutes")
      ? { target_minutes: { dashboard_parameter: "resolution_target_minutes" } }
      : {},
  };
}
