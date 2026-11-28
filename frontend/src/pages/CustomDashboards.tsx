import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, LayoutDashboard, Plus, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuid } from "uuid";
import { Link, useBeforeUnload, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Button } from "@/components/buttons/Button";
import { DashboardRecordDialog, type RecordSelection } from "@/components/dashboards/DashboardRecordTable";
import { DashboardWidgetCard } from "@/components/dashboards/DashboardWidgetCard";
import { dashboardInputClass, DashboardWidgetEditor } from "@/components/dashboards/DashboardWidgetEditor";
import { widgetDefaults } from "@/components/dashboards/dashboardPresentation";
import { DateRangePicker, type DateRangeValue } from "@/components/forms/DateRangePicker";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { useSession } from "@/contexts/sessionContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { useDashboardCatalog, useDashboardDetail, useDashboardEvaluation, useDashboardKeys, useDashboardList } from "@/hooks/useCustomDashboards";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getApiErrorMessage } from "@/services/apiRequestError";
import { ApiError } from "@/types/generated/core/ApiError";
import type { CustomDashboardRead } from "@/types/generated/models/CustomDashboardRead";
import type { DashboardDate } from "@/types/generated/models/DashboardDate";
import type { DashboardDefinition } from "@/types/generated/models/DashboardDefinition";
import type { DashboardWidget } from "@/types/generated/models/DashboardWidget";
import { CustomDashboardsService as api } from "@/types/generated/services/CustomDashboardsService";
import { formatAbsoluteTime } from "@/utils/dateFormatters";
import { formatForBackend, parseRelativeTime } from "@/utils/dateFilters";

const DEFAULT_DATE: DashboardDate = { preset: "last_7_days" };
const DASHBOARD_ROOT = "/dashboards";
const MAX_WIDGETS = 12;
const PRESETS = { last_7_days: "-7d", last_30_days: "-30d", last_90_days: "-90d" } as const;
const SCOPE_LABELS = { personal: "Personal", organization: "Shared with organization", starter: "Starter" };
type Draft = { title: string; definition: DashboardDefinition; revision: number };

function pickerValue(date: DashboardDate): DateRangeValue | null {
  if (date.preset === "custom" && date.start && date.end) {
    return { start: date.start, end: date.end, preset: "custom" };
  }
  const preset = PRESETS[date.preset && date.preset !== "custom" ? date.preset : "last_7_days"];
  const range = parseRelativeTime(preset);
  return range ? { start: formatForBackend(range.start), end: formatForBackend(range.end), preset } : null;
}

function dashboardDate(value: DateRangeValue): DashboardDate {
  const preset = Object.entries(PRESETS).find(([, label]) => label === value.preset)?.[0] as DashboardDate["preset"];
  return preset ? { preset } : { preset: "custom", start: value.start, end: value.end };
}

function normalized(definition: DashboardDefinition): DashboardDefinition {
  return {
    ...definition,
    widgets: definition.widgets?.map((widget) => ({
      ...widget,
      filters: widget.filters?.filter((filter) => filter.value.length),
    })),
  };
}

function dashboardPath(id: string) {
  return `${DASHBOARD_ROOT}/${id}`;
}

function DashboardIndex() {
  const query = useDashboardList();
  const { isAuditor } = useSession();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function create() {
    setBusy(true);
    setError("");
    try {
      const dashboard = await api.createCustomDashboard({
        requestBody: { title: "Untitled dashboard", definition: { schema_version: 1, date: DEFAULT_DATE, widgets: [] } },
      });
      void navigate(`${dashboardPath(dashboard.id)}?edit=1`);
    } catch (failure) {
      setError(getApiErrorMessage(failure, "Could not create dashboard."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-heading-1 font-heading-1">Dashboards</h1>
        {!isAuditor && <Button variant="brand-primary" onClick={() => void create()} disabled={busy} icon={<Plus />}>New dashboard</Button>}
      </header>
      {query.isPending && <p role="status">Loading dashboards…</p>}
      {(error || query.isError) && <p role="alert">{error || getApiErrorMessage(query.error, "Could not load dashboards.")}</p>}
      {query.data && (["starter", "personal", "organization"] as const).map((scope) => {
        const dashboards = query.data.filter((dashboard) => dashboard.scope === scope);
        if (!dashboards.length) return null;
        return (
          <section key={scope} className="flex flex-col gap-3">
            <h2 className="text-heading-2 font-heading-2">
              {scope === "starter" ? "Starter dashboards" : scope === "personal" ? "My dashboards" : "Shared dashboards"}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {dashboards.map((dashboard) => (
                <Link key={dashboard.id} to={dashboardPath(dashboard.id)} className="flex items-center gap-3 rounded-lg border border-neutral-border bg-default-background p-4 hover:bg-neutral-100 focus-visible:outline">
                  <LayoutDashboard aria-hidden="true" className="size-5 shrink-0 text-subtext-color" />
                  <span className="text-body-bold font-body-bold">{dashboard.title}</span>
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}

function initialDraft(key: string, dashboard: CustomDashboardRead, startEditing: boolean): Draft | null {
  if (!dashboard.can_edit) return null;
  try {
    const stored: Draft | null = JSON.parse(sessionStorage.getItem(key) ?? "null");
    if (stored?.definition && stored.title != null && Number.isInteger(stored.revision)) return stored;
  } catch {
    // Session storage can be unavailable in a restricted browser.
  }
  return startEditing ? { title: dashboard.title, definition: dashboard.definition, revision: dashboard.revision } : null;
}

function DashboardCanvas({ dashboard }: { dashboard: CustomDashboardRead }) {
  const { isAdmin, isAuditor, session } = useSession();
  const { timezonePreference } = useTimezonePreference();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const keys = useDashboardKeys();
  const catalog = useDashboardCatalog();
  const draftKey = `intercept.dashboard-draft.${session?.sessionId}.${dashboard.id}`;
  const [draft, setDraft] = useState(() => initialDraft(draftKey, dashboard, params.has("edit")));
  const [dateOverride, setDateOverride] = useState<DashboardDate>();
  const [selected, setSelected] = useState<string>();
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<RecordSelection>();
  const dragging = useRef<string | undefined>(undefined);
  const inspector = useRef<HTMLDivElement>(null);
  const activeDraft = dashboard.can_edit ? draft : null;
  const dirty = activeDraft != null && (
    activeDraft.title !== dashboard.title || JSON.stringify(activeDraft.definition) !== JSON.stringify(dashboard.definition)
  );
  const definition = activeDraft?.definition ?? dashboard.definition;
  const widgets = [...(definition.widgets ?? [])].sort((a, b) => a.layout.order - b.layout.order);
  const selectedWidget = widgets.find((widget) => widget.id === selected);
  const measures = catalog.data ?? [];
  const timezone = timezonePreference === "utc" ? "UTC" : Intl.DateTimeFormat().resolvedOptions().timeZone;
  const date = activeDraft ? definition.date ?? DEFAULT_DATE : dateOverride ?? definition.date ?? DEFAULT_DATE;
  const picker = useMemo(() => pickerValue(date), [date]);
  const request = useMemo(() => ({
    definition: normalized(definition),
    date,
    timezone,
    dashboard_id: dashboard.id,
    revision: dashboard.revision,
  }), [date, definition, timezone, dashboard.id, dashboard.revision]);
  const evaluation = useDashboardEvaluation(request);
  const refreshing = evaluation.isFetching || evaluation.pendingEdit;
  const results = evaluation.data?.response.results;
  const evaluatedWidgets = evaluation.data?.request.definition.widgets;
  const asOf = evaluation.data && formatAbsoluteTime(evaluation.data.response.evaluated_at, "MMM d, HH:mm:ss", timezonePreference);
  const conflict = activeDraft != null && activeDraft.revision !== dashboard.revision;
  const visibleEditor = activeDraft != null && !preview;

  useEffect(() => {
    try {
      if (activeDraft && dirty) sessionStorage.setItem(draftKey, JSON.stringify(activeDraft));
      else sessionStorage.removeItem(draftKey);
    } catch {
      // The current canvas still retains the draft in memory.
    }
  }, [activeDraft, dirty, draftKey]);

  useEffect(() => {
    if (!visibleEditor || !selected || window.matchMedia("(min-width: 1024px)").matches) return;
    inspector.current?.scrollIntoView({ block: "nearest" });
  }, [selected, visibleEditor]);

  useBeforeUnload((event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  useEffect(() => {
    if (!dirty) return;
    function confirmNavigation(event: MouseEvent) {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!link || link.hasAttribute("data-dashboard-record") || link.getAttribute("target") === "_blank") return;
      if (!window.confirm("Leave this dashboard? Your draft will be available when you return.")) event.preventDefault();
    }
    document.addEventListener("click", confirmNavigation, true);
    return () => document.removeEventListener("click", confirmNavigation, true);
  }, [dirty]);

  function changeDefinition(next: DashboardDefinition) {
    setDraft((current) => current && { ...current, definition: next });
  }

  function changeWidgets(next: DashboardWidget[]) {
    const parameters = next.some((widget) => typeof widget.parameters?.target_minutes === "object" && widget.parameters.target_minutes != null)
      && definition.parameters?.resolution_target_minutes == null
      ? { resolution_target_minutes: 1440 }
      : definition.parameters;
    changeDefinition({
      ...definition,
      parameters,
      widgets: next.map((widget, order) => ({ ...widget, layout: { ...widget.layout, order } })),
    });
  }

  function addWidget(source?: DashboardWidget) {
    if (widgets.length >= MAX_WIDGETS || !measures.length) return;
    const widget = source
      ? { ...source, id: uuid(), title: `${source.title.slice(0, 95)} copy` }
      : { id: uuid(), ...widgetDefaults(measures[0]), layout: { order: widgets.length, width: "half" as const } };
    changeWidgets([...widgets, widget]);
    setSelected(widget.id);
  }

  function moveWidget(id: string, to: number) {
    const from = widgets.findIndex((widget) => widget.id === id);
    if (from < 0 || to < 0 || to >= widgets.length || from === to) return;
    const next = [...widgets];
    next.splice(to, 0, next.splice(from, 1)[0]);
    changeWidgets(next);
  }

  function startEdit() {
    setDraft({ title: dashboard.title, definition: dashboard.definition, revision: dashboard.revision });
    setPreview(false);
    setError("");
  }

  function finishEdit() {
    setDraft(null);
    setPreview(false);
    setSelected(undefined);
    setError("");
    if (params.has("edit")) {
      const next = new URLSearchParams(params);
      next.delete("edit");
      setParams(next, { replace: true });
    }
  }

  async function mutate(action: () => PromiseLike<CustomDashboardRead>, openCopy = false) {
    setBusy(true);
    setError("");
    try {
      const result = await action();
      client.setQueryData(keys.detail(result.id), result);
      void client.invalidateQueries({ queryKey: keys.list });
      if (result.id !== dashboard.id) {
        if (!openCopy) finishEdit();
        void navigate(`${dashboardPath(result.id)}${openCopy ? "?edit=1" : ""}`);
      } else finishEdit();
    } catch (failure) {
      setError(getApiErrorMessage(failure, "Could not save the dashboard."));
      if (failure instanceof ApiError && failure.status === 409) {
        void client.invalidateQueries({ queryKey: keys.detail(dashboard.id) });
      }
    } finally {
      setBusy(false);
    }
  }

  function save(asCopy = false, publish = false) {
    const title = activeDraft?.title ?? dashboard.title;
    const scope = publish || dashboard.scope === "organization" ? "organization" : "personal";
    const input = { title, definition: normalized(definition) };
    return mutate(() => asCopy
      ? api.createCustomDashboard({ requestBody: { ...input, scope: "personal" } })
      : api.updateCustomDashboard({
          identifier: dashboard.id,
          requestBody: { ...input, scope, revision: activeDraft?.revision ?? dashboard.revision },
        }));
  }

  async function deleteDashboard() {
    if (!window.confirm(`Delete “${dashboard.title}”?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteCustomDashboard({ identifier: dashboard.id, revision: dashboard.revision });
      void client.invalidateQueries({ queryKey: keys.list });
      void navigate(DASHBOARD_ROOT);
    } catch (failure) {
      setError(getApiErrorMessage(failure, "Could not delete the dashboard."));
      setBusy(false);
    }
  }

  const valid = Boolean(activeDraft?.title.trim()) && widgets.every((widget) => widget.title.trim());
  const failed = results?.filter((result) => result.error).length ?? 0;
  return (
    <>
      <header className="flex flex-col gap-3">
        <Link to={DASHBOARD_ROOT} className="flex w-fit items-center gap-1 text-body text-subtext-color hover:underline">
          <ArrowLeft className="size-4" aria-hidden="true" /> Dashboards
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="break-words text-heading-1 font-heading-1">{activeDraft?.title || dashboard.title}</h1>
            <p className="mt-1 text-caption text-subtext-color">{SCOPE_LABELS[dashboard.scope]}{activeDraft ? " · Editing draft" : ""}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeDraft ? (
              <>
                <Button variant="neutral-secondary" onClick={() => setPreview(!preview)}>{preview ? "Continue editing" : "Preview dashboard"}</Button>
                <Button variant="neutral-secondary" onClick={finishEdit} disabled={busy}>Cancel</Button>
                <Button variant="brand-primary" onClick={() => void save()} disabled={busy || !valid || conflict}>Save</Button>
              </>
            ) : (
              <>
                {!isAuditor && (
                  <Button variant={dashboard.can_edit ? "neutral-secondary" : "brand-primary"} disabled={busy} onClick={() => void mutate(
                    () => api.duplicateCustomDashboard({ identifier: dashboard.id, requestBody: {} }), true,
                  )}>Duplicate and edit</Button>
                )}
                {dashboard.can_edit && <Button variant="brand-primary" onClick={startEdit}>Edit dashboard</Button>}
                {isAdmin && dashboard.can_edit && dashboard.scope === "personal" && (
                  <Button variant="neutral-secondary" disabled={busy} onClick={() => {
                    if (window.confirm("Publish this dashboard so everyone in this Intercept deployment can view it?")) void save(false, true);
                  }}>Publish to organization</Button>
                )}
                {dashboard.can_edit && <Button variant="neutral-tertiary" disabled={busy} onClick={() => void deleteDashboard()}>Delete</Button>}
              </>
            )}
          </div>
        </div>
      </header>

      {(error || evaluation.isError || catalog.isError) && (
        <p role="alert" className="rounded border border-neutral-border p-3">
          {error || getApiErrorMessage(evaluation.error ?? catalog.error, "Could not load dashboard.")}
        </p>
      )}
      {conflict && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded border border-neutral-border p-3">
          <span>The saved dashboard changed while you were editing.</span>
          <Button variant="neutral-secondary" onClick={startEdit}>Reload saved version</Button>
          <Button variant="brand-primary" disabled={busy || !valid} onClick={() => void save(true)}>Save as personal copy</Button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-neutral-border py-3">
        <div className="flex flex-wrap items-center gap-2">
          <DateRangePicker
            value={picker}
            onChange={(value) => {
              if (!value) return;
              if (activeDraft) changeDefinition({ ...definition, date: dashboardDate(value) });
              else setDateOverride(dashboardDate(value));
            }}
            presets={Object.values(PRESETS)}
            showAllTime={false}
            size="small"
          />
          {widgets.length > 0 && (
            <Button variant="neutral-secondary" size="small" disabled={refreshing} onClick={() => void evaluation.refetch()} icon={<RefreshCw />}>Refresh</Button>
          )}
          {visibleEditor && (
            <Button variant="neutral-secondary" size="small" disabled={widgets.length >= MAX_WIDGETS || !measures.length} onClick={() => addWidget()} icon={<Plus />}>Add widget</Button>
          )}
        </div>
        {widgets.length > 0 && (
          <p role="status" className="text-caption text-subtext-color">
            {refreshing ? "Refreshing…" : evaluation.isError ? "Refresh failed" : asOf && failed < widgets.length ? `Last refreshed ${asOf}` : "No current results"}
            {refreshing && asOf ? ` · showing results from ${asOf}` : ""}
            {failed > 0 && !refreshing ? ` · ${failed} ${failed === 1 ? "widget" : "widgets"} failed` : ""}
          </p>
        )}
      </div>

      {visibleEditor && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-body">
            Dashboard name
            <input className={dashboardInputClass} maxLength={100} value={activeDraft.title} onChange={(event) => setDraft({ ...activeDraft, title: event.target.value })} />
          </label>
          {definition.parameters?.resolution_target_minutes != null && (
            <label className="flex flex-col gap-1 text-body">
              Resolution target (minutes)
              <input
                className={dashboardInputClass}
                type="number" min={1} max={525600} step={1}
                value={definition.parameters.resolution_target_minutes ?? ""}
                onChange={(event) => changeDefinition({ ...definition, parameters: { resolution_target_minutes: Number(event.target.value) } })}
              />
            </label>
          )}
        </div>
      )}

      <div className={`grid items-start gap-4 ${visibleEditor && selectedWidget ? "lg:grid-cols-[minmax(0,1fr)_minmax(17rem,22rem)]" : ""}`}>
        <div className="grid min-w-0 items-start gap-4 md:grid-cols-2">
          {widgets.length === 0 && (
            <p className="rounded-lg border border-neutral-border p-6 text-body text-subtext-color">This dashboard has no widgets. {visibleEditor ? "Add a widget to get started." : "Edit the dashboard to add a widget."}</p>
          )}
          {widgets.map((widget, index) => {
            const measure = measures.find((entry) => entry.id === widget.measure);
            const target = widget.parameters?.target_minutes;
            const evaluated = evaluatedWidgets?.find((item) => item.id === widget.id);
            const current = request.definition.widgets?.find((item) => item.id === widget.id);
            const result = JSON.stringify(evaluated) === JSON.stringify(current)
              ? results?.find((item) => item.widget_id === widget.id)
              : undefined;
            return (
              <div key={widget.id} className={`min-w-0 ${widget.layout.width === "wide" ? "md:col-span-2" : ""}`}
                onDragOver={visibleEditor ? (event) => event.preventDefault() : undefined}
                onDrop={visibleEditor ? (event) => {
                  event.preventDefault();
                  if (dragging.current) moveWidget(dragging.current, index);
                  dragging.current = undefined;
                } : undefined}
              >
                {visibleEditor && (
                  <button
                    type="button"
                    draggable
                    onDragStart={(event) => {
                      dragging.current = widget.id;
                      event.dataTransfer.setData("text/plain", widget.id);
                      event.dataTransfer.effectAllowed = "move";
                    }}
                    onDragEnd={() => { dragging.current = undefined; }}
                    onClick={() => setSelected(widget.id)}
                    className="mb-1 cursor-grab rounded px-2 py-1 text-caption text-subtext-color hover:bg-neutral-100 focus-visible:outline"
                    aria-label={`Reorder ${widget.title}`}
                  >Drag to reorder</button>
                )}
                <DashboardWidgetCard
                  widget={widget}
                  measure={measure}
                  result={result}
                  pending={refreshing}
                  target={typeof target === "number" ? target : target ? definition.parameters?.resolution_target_minutes : null}
                  selected={visibleEditor && selected === widget.id}
                  asOf={asOf || undefined}
                  onEdit={visibleEditor ? () => setSelected(widget.id) : undefined}
                  onDrill={!refreshing ? setSelection : undefined}
                />
              </div>
            );
          })}
        </div>
        {visibleEditor && selectedWidget && (
          <div ref={inspector} className="lg:sticky lg:top-4 lg:max-h-[calc(100dvh-2rem)] lg:overflow-auto">
            <DashboardWidgetEditor
              key={selectedWidget.id}
              widget={selectedWidget}
              measures={measures}
              update={(next) => changeWidgets(widgets.map((widget) => widget.id === next.id ? next : widget))}
              remove={() => {
                changeWidgets(widgets.filter((widget) => widget.id !== selectedWidget.id));
                setSelected(undefined);
              }}
              duplicate={() => addWidget(selectedWidget)}
              move={(offset) => moveWidget(selectedWidget.id, widgets.indexOf(selectedWidget) + offset)}
              canMoveUp={widgets.indexOf(selectedWidget) > 0}
              canMoveDown={widgets.indexOf(selectedWidget) < widgets.length - 1}
              atLimit={widgets.length >= MAX_WIDGETS}
            />
          </div>
        )}
      </div>
      {selection && <DashboardRecordDialog key={selection.reference} selection={selection} onClose={() => setSelection(undefined)} />}
    </>
  );
}

function DashboardDetail({ id }: { id: string }) {
  const query = useDashboardDetail(id);
  if (query.isPending) return <p role="status">Loading dashboard…</p>;
  if (query.isError) return <p role="alert">{getApiErrorMessage(query.error, "Could not load dashboard.")} <Link className="underline" to={DASHBOARD_ROOT}>Back to dashboards</Link></p>;
  return <DashboardCanvas key={id} dashboard={query.data} />;
}

export default function CustomDashboards() {
  useDocumentTitle("Dashboards");
  const { dashboardId } = useParams();
  return (
    <DefaultPageLayout withContainer>
      <main className="mx-auto flex min-h-full w-full max-w-[1536px] flex-col gap-5 px-6 py-8 mobile:px-4">
        {dashboardId ? <DashboardDetail key={dashboardId} id={dashboardId} /> : <DashboardIndex />}
      </main>
    </DefaultPageLayout>
  );
}
