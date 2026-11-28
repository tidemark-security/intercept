import { useState } from "react";

import { Button } from "@/components/buttons/Button";
import type { DashboardFilter } from "@/types/generated/models/DashboardFilter";
import type { DashboardMeasure } from "@/types/generated/models/DashboardMeasure";
import type { DashboardWidget } from "@/types/generated/models/DashboardWidget";
import { DATE_BASIS, DISPLAY_LABELS, fieldLabel, widgetDefaults } from "./dashboardPresentation";

export const dashboardInputClass = "min-w-0 rounded border border-neutral-border bg-default-background px-2 py-1.5 text-body text-default-font focus-visible:outline-focus-border";

function FilterInput({
  condition, option, update, remove,
}: {
  condition: DashboardFilter;
  option: DashboardMeasure["filters"][number];
  update: (value: DashboardFilter) => void;
  remove: () => void;
}) {
  const [text, setText] = useState(condition.value.join("\n"));
  const values = option.values ?? [];
  return (
    <fieldset className="flex min-w-0 flex-col gap-2 rounded border border-neutral-border p-2">
      <legend className="px-1 text-caption-bold">{option.label}</legend>
      {option.operators.length > 1 && (
        <select
          className={dashboardInputClass}
          aria-label={`${option.label} operator`}
          value={condition.op}
          onChange={(event) => update({ ...condition, op: event.target.value as DashboardFilter["op"] })}
        >
          <option value="contains_all">Contains all</option>
          <option value="excludes_all">Excludes each</option>
        </select>
      )}
      {values.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <label className="inline-flex items-center gap-1 text-caption" key={value}>
              <input
                type="checkbox"
                checked={condition.value.includes(value)}
                onChange={(event) => update({
                  ...condition,
                  value: event.target.checked
                    ? [...condition.value, value]
                    : condition.value.filter((item) => item !== value),
                })}
              />
              {value}
            </label>
          ))}
        </div>
      ) : (
        <textarea
          className={dashboardInputClass}
          aria-label={`${option.label} values`}
          placeholder={condition.field === "assignee" ? "Username or __unassigned__" : "One exact value per line"}
          rows={2}
          maxLength={3500}
          value={text}
          onChange={(event) => {
            const value = event.target.value;
            setText(value);
            update({ ...condition, value: value.split("\n").map((item) => item.trim()).filter(Boolean) });
          }}
        />
      )}
      <Button size="small" variant="neutral-tertiary" onClick={remove}>Remove {option.label.toLowerCase()} filter</Button>
    </fieldset>
  );
}

export function DashboardWidgetEditor({
  widget, measures, update, remove, duplicate, move, canMoveUp, canMoveDown, atLimit,
}: {
  widget: DashboardWidget;
  measures: DashboardMeasure[];
  update: (widget: DashboardWidget) => void;
  remove: () => void;
  duplicate: () => void;
  move: (offset: number) => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
  atLimit: boolean;
}) {
  const measure = measures.find((entry) => entry.id === widget.measure);
  const [newFilter, setNewFilter] = useState("");
  if (!measure) return <p>Measure unavailable.</p>;

  const groups = widget.display === "trend" ? ["day", "week"] : measure.dimensions;
  const columns = widget.table?.columns ?? measure.record_columns.slice(0, 6);
  const filters = widget.filters ?? [];
  const addOptions = measure.filters.filter((option) => !filters.some((filter) => filter.field === option.field));
  const changeDisplay = (display: DashboardWidget["display"]) => update({
    ...widget,
    display,
    group_by: display === "trend" ? "day" : display === "breakdown" ? measure.dimensions[0] : null,
    table: display === "table" ? widget.table : null,
  });

  return (
    <aside className="flex min-w-0 flex-col gap-3 rounded-lg border border-neutral-border bg-default-background p-4" aria-label="Widget settings">
      <h2 className="text-heading-3 font-heading-3">Widget settings</h2>
      <label className="flex flex-col gap-1">
        Widget title
        <input className={dashboardInputClass} value={widget.title} maxLength={100} onChange={(event) => update({ ...widget, title: event.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        Measure
        <select
          className={dashboardInputClass}
          aria-label="Measure"
          value={widget.measure}
          onChange={(event) => {
            const next = measures.find((entry) => entry.id === event.target.value);
            if (next) update({ id: widget.id, layout: widget.layout, ...widgetDefaults(next) });
          }}
        >
          {(["alerts", "cases", "tasks"] as const).map((entity) => (
            <optgroup key={entity} label={fieldLabel(entity)}>
              {measures.filter((entry) => entry.entity === entity).map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      <p className="text-caption text-subtext-color">{measure.description} {DATE_BASIS[measure.date_basis]}.</p>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex min-w-0 flex-col gap-1">
          Display
          <select className={dashboardInputClass} aria-label="Display" value={widget.display} onChange={(event) => changeDisplay(event.target.value as DashboardWidget["display"])}>
            {measure.displays.map((display) => <option value={display} key={display}>{DISPLAY_LABELS[display]}</option>)}
          </select>
        </label>
        {widget.display !== "number" && (
          <label className="flex min-w-0 flex-col gap-1">
            Group by
            <select
              className={dashboardInputClass}
              aria-label="Group by"
              value={widget.group_by ?? ""}
              onChange={(event) => update({ ...widget, group_by: event.target.value || null, table: null })}
            >
              {widget.display === "table" && <option value="">Matching records</option>}
              {groups.map((group) => <option key={group} value={group}>{fieldLabel(group)}</option>)}
            </select>
          </label>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex min-w-0 flex-col gap-1">
          Width
          <select
            className={dashboardInputClass}
            aria-label="Width"
            value={widget.layout.width ?? "half"}
            onChange={(event) => update({ ...widget, layout: { ...widget.layout, width: event.target.value as "half" | "wide" } })}
          >
            <option value="half">Half</option>
            <option value="wide">Full</option>
          </select>
        </label>
        {measure.aggregations.length > 0 && (
          <label className="flex min-w-0 flex-col gap-1">
            Aggregation
            <select
              className={dashboardInputClass}
              aria-label="Aggregation"
              value={widget.aggregation ?? "p50"}
              onChange={(event) => update({ ...widget, aggregation: event.target.value as DashboardWidget["aggregation"] })}
            >
              <option value="p50">Median (p50)</option>
              <option value="mean">Mean</option>
              <option value="p95">95th percentile</option>
            </select>
          </label>
        )}
      </div>
      {measure.parameters.includes("min_age_minutes") && (
        <label className="flex flex-col gap-1">
          Older than (minutes)
          <input
            type="number" min={0} max={525600} step={1} className={dashboardInputClass}
            value={widget.parameters?.min_age_minutes ?? ""}
            onChange={(event) => update({ ...widget, parameters: { min_age_minutes: event.target.value ? Number(event.target.value) : null } })}
          />
        </label>
      )}
      {measure.parameters.includes("target_minutes") && (
        <label className="flex flex-col gap-1">
          Widget target override (minutes)
          <input
            type="number" min={1} max={525600} step={1} className={dashboardInputClass}
            placeholder="Use dashboard target"
            value={typeof widget.parameters?.target_minutes === "number" ? widget.parameters.target_minutes : ""}
            onChange={(event) => update({
              ...widget,
              parameters: {
                target_minutes: event.target.value ? Number(event.target.value) : { dashboard_parameter: "resolution_target_minutes" },
              },
            })}
          />
        </label>
      )}
      {widget.display === "table" && !widget.group_by && (
        <details>
          <summary className="cursor-pointer">Table columns and sort</summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {measure.record_columns.map((column) => (
              <label className="flex items-center gap-1 text-caption" key={column}>
                <input
                  type="checkbox"
                  checked={columns.includes(column)}
                  disabled={columns.includes(column) ? columns.length === 1 : columns.length === 10}
                  onChange={(event) => update({
                    ...widget,
                    table: {
                      ...widget.table,
                      columns: event.target.checked ? [...columns, column] : columns.filter((item) => item !== column),
                    },
                  })}
                />
                {fieldLabel(column)}
              </label>
            ))}
          </div>
          <label className="mt-2 flex flex-col gap-1">
            Sort by
            <select
              className={dashboardInputClass}
              aria-label="Sort by"
              value={widget.table?.sort?.field ?? "created_at"}
              onChange={(event) => update({ ...widget, table: { columns, sort: { field: event.target.value, direction: widget.table?.sort?.direction ?? "desc" } } })}
            >
              {measure.record_columns.map((column) => <option value={column} key={column}>{fieldLabel(column)}</option>)}
            </select>
          </label>
          <label className="mt-2 flex flex-col gap-1">
            Sort direction
            <select
              className={dashboardInputClass}
              aria-label="Sort direction"
              value={widget.table?.sort?.direction ?? "desc"}
              onChange={(event) => update({
                ...widget, table: { columns, sort: { field: widget.table?.sort?.field ?? "created_at", direction: event.target.value as "asc" | "desc" } },
              })}
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
        </details>
      )}
      <div className="border-t border-neutral-border pt-3">
        <h3 className="mb-2 text-body-bold">Filters</h3>
        <div className="flex flex-col gap-2">
          {filters.map((condition, index) => {
            const option = measure.filters.find((item) => item.field === condition.field);
            return option && (
              <FilterInput
                key={condition.field}
                condition={condition}
                option={option}
                update={(next) => update({ ...widget, filters: filters.map((item, i) => i === index ? next : item) })}
                remove={() => update({ ...widget, filters: filters.filter((_, i) => i !== index) })}
              />
            );
          })}
          {addOptions.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <select className={dashboardInputClass} aria-label="Filter field" value={newFilter} onChange={(event) => setNewFilter(event.target.value)}>
                <option value="">Choose a field</option>
                {addOptions.map((item) => <option key={item.field} value={item.field}>{item.label}</option>)}
              </select>
              <Button
                size="small" variant="neutral-secondary" disabled={!newFilter}
                onClick={() => {
                  const option = addOptions.find((item) => item.field === newFilter);
                  if (!option) return;
                  update({ ...widget, filters: [...filters, { field: option.field as DashboardFilter["field"], op: option.operators[0] as DashboardFilter["op"], value: [] }] });
                  setNewFilter("");
                }}
              >Add filter</Button>
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-1 border-t border-neutral-border pt-3">
        <Button size="small" variant="neutral-secondary" disabled={!canMoveUp} onClick={() => move(-1)}>Move up</Button>
        <Button size="small" variant="neutral-secondary" disabled={!canMoveDown} onClick={() => move(1)}>Move down</Button>
        <Button size="small" variant="neutral-secondary" disabled={atLimit} onClick={duplicate}>Duplicate widget</Button>
        <Button size="small" variant="neutral-tertiary" onClick={remove}>Remove widget</Button>
      </div>
    </aside>
  );
}
