import { BarChart } from "@tidemark-security/ux";
import { useState } from "react";

import { Button } from "@/components/buttons/Button";
import { Table } from "@/components/data-display/Table";
import type { DashboardMeasure } from "@/types/generated/models/DashboardMeasure";
import type { DashboardPoint } from "@/types/generated/models/DashboardPoint";
import type { DashboardResult } from "@/types/generated/models/DashboardResult";
import type { DashboardWidget } from "@/types/generated/models/DashboardWidget";
import { DATE_BASIS, fieldLabel, metricValue } from "./dashboardPresentation";
import { DashboardRecordTable, type RecordSelection } from "./DashboardRecordTable";

const chartColor = "rgb(var(--color-brand-primary))";

function chartData(points: DashboardPoint[], weekly: boolean) {
  const byDay = new Map(points.map((point) => [point.group, point]));
  const start = points[0]?.group;
  const end = points.at(-1)?.group;
  if (!start || !end) return [];
  const data = [];
  const date = new Date(`${start}T00:00:00Z`);
  while (date.toISOString().slice(0, 10) <= end) {
    const day = date.toISOString().slice(0, 10);
    const point = byDay.get(day);
    data.push({ day, value: point?.value, drill: point?.drill });
    date.setUTCDate(date.getUTCDate() + (weekly ? 7 : 1));
  }
  return data;
}

export function DashboardWidgetCard({
  widget, measure, result, pending, target, asOf, onEdit, selected, onDrill,
}: {
  widget: DashboardWidget;
  measure?: DashboardMeasure;
  result?: DashboardResult;
  pending: boolean;
  target?: number | null;
  asOf?: string;
  onEdit?: () => void;
  selected: boolean;
  onDrill?: (selection: RecordSelection) => void;
}) {
  const [period, setPeriod] = useState("");
  const points = result?.points ?? [];
  const format = (value?: number | null) => metricValue(value, measure?.unit);
  const first = points[0];
  const open = (drill: string, label?: string) => onDrill?.({
    reference: drill,
    title: label ? `${widget.title} · ${label}` : widget.title,
  });
  const sample = points.find((point) => point.group === period) ?? first;
  const largest = Math.max(1, ...points.map((point) => point.value ?? 0));
  const content = () => {
    if (result?.error) return <p role="alert" className="py-4 text-body">{result.error}</p>;
    if (!result) return <p className="py-4 text-body text-subtext-color">{pending ? "Loading…" : "Results unavailable"}</p>;
    if (result.records && first) {
      return (
        <>
          <DashboardRecordTable records={result.records} limit={6} />
          <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(first.drill)}>
            View records ({first.count.toLocaleString()})
          </Button>
        </>
      );
    }
    if (!points.length || !first) return <p className="py-4 text-body text-subtext-color">No matching records in this range.</p>;
    if (widget.display === "number") {
      return (
        <div className="flex flex-wrap items-end justify-between gap-3 pt-2">
          <div>
            <p className="text-heading-1 font-heading-1 tabular-nums">{format(first.value)}</p>
            {(measure?.unit === "seconds" || first.eligible_count != null) && (
              <p className="text-caption text-subtext-color">
                {first.eligible_count != null
                  ? `${first.count.toLocaleString()} of ${first.eligible_count.toLocaleString()} eligible`
                  : `${first.count.toLocaleString()} valid samples`}
                {!!first.excluded_count && ` · ${first.excluded_count.toLocaleString()} invalid timestamps excluded`}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(first.drill)}>View records</Button>
            {first.eligible_drill && (
              <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(first.eligible_drill!, "All eligible records")}>
                All eligible records
              </Button>
            )}
          </div>
        </div>
      );
    }
    if (widget.display === "trend") {
      return (
        <>
          <BarChart
            data={chartData(points, widget.group_by === "week")}
            series={[{ dataKey: "value", color: chartColor, name: measure?.label ?? "Value" }]}
            xAxisKey="day"
            height={200}
            showLegend={false}
            onChartClick={(entry) => {
              if (typeof entry.drill === "string") open(entry.drill, String(entry.day));
            }}
            tooltipFormatter={(value) => format(typeof value === "number" ? value : null)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label={`Period for ${widget.title}`}
              className="rounded border border-neutral-border bg-default-background px-2 py-1 text-body"
              value={sample?.group ?? ""}
              onChange={(event) => setPeriod(event.target.value)}
            >
              {points.map((point) => <option key={point.group} value={point.group ?? ""}>{point.group} · {format(point.value)}{point.excluded_count ? ` · ${point.excluded_count} excluded` : ""}</option>)}
            </select>
            {sample && <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(sample.drill, sample.group ?? undefined)}>View records</Button>}
            {sample?.eligible_drill && (
              <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(sample.eligible_drill!, "All eligible records")}>All eligible records</Button>
            )}
          </div>
        </>
      );
    }
    const actions = (point: DashboardPoint) => (
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        {point.eligible_drill && (
          <Button size="small" variant="neutral-tertiary" disabled={!onDrill} onClick={() => open(point.eligible_drill!, `${point.group ?? "Unknown"} · All eligible`)}>
            {point.eligible_count?.toLocaleString()} eligible
          </Button>
        )}
      </div>
    );
    if (widget.display === "table") {
      return (
        <div className="max-h-72 overflow-auto">
          <Table header={<Table.HeaderRow><Table.HeaderCell>{fieldLabel(widget.group_by ?? "Group")}</Table.HeaderCell><Table.HeaderCell>Value</Table.HeaderCell><Table.HeaderCell>Records</Table.HeaderCell></Table.HeaderRow>}>
            {points.map((point) => (
              <Table.Row key={point.drill}>
                <Table.Cell>{point.group ?? "Unknown"}</Table.Cell>
                <Table.Cell>{format(point.value)}</Table.Cell>
                <Table.Cell>
                  <Button size="small" variant="neutral-secondary" disabled={!onDrill} onClick={() => open(point.drill, point.group ?? "Unknown")}>
                    {point.count.toLocaleString()} records
                  </Button>
                  {actions(point)}
                </Table.Cell>
              </Table.Row>
            ))}
          </Table>
        </div>
      );
    }
    return (
      <div className="flex max-h-72 flex-col gap-1 overflow-auto">
        {points.map((point) => (
          <div key={point.drill} className="flex items-center gap-2">
            <button
              type="button"
              className="flex min-w-0 flex-1 flex-col gap-1 rounded p-2 text-left hover:bg-neutral-100 focus-visible:outline"
              disabled={!onDrill}
              onClick={() => open(point.drill, point.group ?? "Unknown")}
            >
              <span className="flex w-full items-baseline justify-between gap-2">
                <span className="min-w-0 break-words">{point.group ?? "Unknown"}</span>
                <span className="shrink-0 font-body-bold tabular-nums">{format(point.value)}</span>
              </span>
              <span className="h-2 w-full rounded bg-neutral-200">
                <span className="block h-2 rounded bg-brand-primary" style={{ width: `${100 * (point.value ?? 0) / largest}%` }} />
              </span>
            </button>
            {actions(point)}
          </div>
        ))}
      </div>
    );
  };

  return (
    <section className={`min-w-0 rounded-lg border bg-default-background p-4 ${selected ? "border-brand-primary" : "border-neutral-border"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-heading-3 font-heading-3">{widget.title}</h2>
          {measure && (
            <p className="text-caption text-subtext-color" title={measure.description}>
              {DATE_BASIS[measure.date_basis]}
              {measure.date_basis === "current" && asOf ? ` · ${asOf}` : ""}
              {target != null ? ` · ${metricValue(target * 60, "seconds")} target` : ""}
            </p>
          )}
        </div>
        {onEdit && <Button size="small" variant="neutral-secondary" onClick={onEdit} aria-label={`Edit ${widget.title}`}>Edit</Button>}
      </div>
      {measure?.entity === "alerts" && widget.group_by === "title" && (
        <p className="text-caption text-subtext-color">Grouped by alert title as a proxy for detection rule.</p>
      )}
      <div className="mt-3 flex flex-col items-stretch gap-3">
        {content()}
        {result?.truncated && <p className="text-caption text-subtext-color">Showing the top 50 groups.</p>}
      </div>
    </section>
  );
}
