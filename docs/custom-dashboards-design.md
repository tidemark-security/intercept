# Custom dashboards for Intercept

Design baseline: [`release/v0.6.0` at `d2ecd82`](https://github.com/tidemark-security/intercept/commit/d2ecd82c5aa0c852127ddab867150083ea1ec23d).

## MVP

Add **Dashboards** beside Reports in the signed-in navigation. A senior analyst or SOC manager can open either starter, choose **Duplicate and edit**, change a widget or add one, preview its live results, and save a personal copy. A manager with the existing admin role can publish a dashboard to the deployment. Shared dashboards open in view mode and can be duplicated by editors. Keep Home and Reports available for their existing workflows.

Each widget selects one measure over alerts, cases or tasks. The builder offers a compatible grouping, typed filters, and one of four displays: **Number**, **Trend**, **Breakdown**, or **Table**. Number shows one value, Trend buckets an event or cohort by time, Breakdown compares a single categorical dimension, and Table shows grouped rows or matching records. The MVP supports one categorical grouping, fixed grid sizes and approved measures. The same widget definition drives the designer, viewer and drill-down.

### Triage Queue Health

Default range: last seven days. Current queue widgets cover the entire current queue, including alerts older than seven days, and carry an **As of now** label.

| Widget | Question and linked records |
| --- | --- |
| Awaiting triage and over 24 hours | Two number widgets count `NEW` and `IN_PROGRESS` alerts. The second uses a 24-hour age threshold. Each opens its matching alerts. |
| Oldest alerts awaiting triage | Table ordered by creation time ascending, with alert ID, age, priority, assignee and source. Each row opens the alert. |
| Alert intake trend | Daily created alerts in the selected range. Clicking a day opens alerts created in that bucket. |
| Intake by alert title | Breakdown of received alerts by exact title, with a source filter and source as an alternate grouping. Clicking a bar lists the contributing alerts. Title is a rule proxy. Rename or dynamic titles can split counts, and shared titles can merge unrelated rules. |
| Recorded triage time | Median recorded triage duration by recorded triage day. Clicking a point shows the samples and their durations. |

### Case Response Performance

Default range: last 30 days. The starter uses a **24-hour calendar-time resolution target** as an editable example. The target is displayed on affected widgets.

| Widget | Question and linked records |
| --- | --- |
| Time to recorded resolution | Median number and daily trend of time from case creation to recorded closure for currently closed cases. Show sample count and offer mean and p95 in the measure picker. |
| Resolution target missed | Count and percentage of eligible closed cases that exceeded the target, with a priority breakdown. A percentage opens the missed cases by default and offers an **All eligible cases** denominator view. |
| Open cases past target | Current open cases whose age exceeds the target. Table shows elapsed time, target, priority and assignee, with the longest overdue first. Reopened cases can appear here. |
| Overdue follow-up tasks | Current `TODO` or `IN_PROGRESS` tasks with a passed due date. The table shows due date, assignee and linked case when present. Standalone tasks are eligible. |

Label recorded resolution explicitly. The starter answers how long cases take to close and which cases missed a reporting target. A separate first-response clock and historical SLA compliance require additional capture.

## Release baseline and reuse

| Area | What the release supports |
| --- | --- |
| Alerts | One row per alert with creation and update time, status, priority, assignee, title, source, tags, optional `case_id` and `linked_at`, and mutable `triaged_at`. The model has no stable detection-rule ID or canonical duplicate FK. The existing metrics route groups by source, title or tag. [Alert schema](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/models/models.py#L904-L969), [alert metrics route](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/soc_metrics.py#L241-L265), [duplicate handling](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_service.py#L973-L984) |
| Cases | One row per case with status, priority, assignee, tags, creation time and mutable `closed_at`. A transition into `CLOSED` sets the timestamp unless an authorized migration override is supplied. A reopen leaves the stored value behind, so a closure query must test status as well. Case updates record structured status changes. Alert escalation can create a case already in progress. [Case schema](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/models/models.py#L731-L777), [case update](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L334-L380), [case creation from alert](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_triage_apply_service.py#L70-L99) |
| Tasks | One row per task with status, priority, assignee, tags, due date, creation time, optional case and source runbook. There is no completion timestamp column. Ordinary changes can produce audit diffs and timeline notes. Case closure writes child timeline entries and updates status. [Task schema](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/models/models.py#L1554-L1617), [task update](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/task_service.py#L388-L423), [case closure cascade](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L437-L509) |
| Metrics | Reports already has range selection, timezone display, cards, charts, and refresh metadata. Existing SOC, analyst and alert views are scheduled 15-minute aggregates. SOC time series use creation cohorts and current stored outcomes. The summary averages window timing statistics, which cannot produce exact range percentiles. The release service also contains live open-count queries. Reuse date parsing, UI, status sets and applicable outcome conventions. Build the new drillable metrics from scoped records. [Reports](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/frontend/src/pages/Reports.tsx#L3-L23), [view definitions](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/db_migrations/versions/001_initial_schema.py#L506-L605), [refresh schedule](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/db_migrations/versions/001_initial_schema.py#L67-L81), [summary math](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/metrics_service.py#L553-L650) |
| Records and filters | Alerts, CaseList and TaskList use `useURLFilters` and paginated entity hooks. Reuse their filters and record navigation where semantics match. List date parameters filter creation time. Alert source uses a substring match and text search can match fields besides title. Reuse the row/detail UI for exact grouping, duration, and event-date drill-downs. [URL filters](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/frontend/src/hooks/useURLFilters.ts#L13), [alerts list query](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_service.py#L257-L327), [cases list query](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L205-L267), [tasks list route](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/tasks.py#L91-L125) |
| Access and sharing | The three entity routers require an authenticated user, and mutations generally apply the non-auditor check. Analyst performance metrics require admin. The role enum has analyst, admin and auditor. Saved queue filters implement personal and deployment-wide scopes, with admin-controlled organization filters. Use that boundary for MVP team sharing. [Alert router](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/alerts.py#L45), [case router](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/cases.py#L58), [task router](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/tasks.py#L49), [roles](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/models/enums.py#L334-L337), [analyst metrics gate](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/soc_metrics.py#L217-L232), [saved filters](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/saved_filters.py#L28-L72) |

## Measure catalog

Own measure definitions in a backend service. Each stable ID declares its record grain, eligible rows, date basis, unit, aggregation, allowed views, dimensions, filters, typed parameters, data coverage and drill-down predicate. Publish viewer-filtered metadata over the API so the designer and metric help use the same definitions. Once published, changing a measure's meaning requires adding a new measure version or explicitly migrating saved configs.

| Measure IDs | Grain, clock and eligible records |
| --- | --- |
| `alerts.received`, `cases.created`, `tasks.created` | One row per record, bucketed by creation. Duplicate alerts count as received workload. Labels describe the retained records in scope. |
| `alerts.awaiting_triage`, `cases.open`, `tasks.open` | Current records in the configured open states. Alerts use `NEW` and `IN_PROGRESS`, cases use the same names, tasks use `TODO` and `IN_PROGRESS`. Current age is a single evaluation timestamp minus creation time. Allow an optional minimum age on alert queue metrics. Escalated alerts are outside the triage queue even when their case remains open. |
| `alerts.recorded_triage_time` | Calendar time from `created_at` to the current recorded `triaged_at`, grouped by that timestamp. Include valid recorded samples; label that duplicate closures can contribute to measured triage effort. Show valid sample count and missing/invalid coverage where the eligible cohort is known. This timestamp can be stamped by triage, linking or subsequent resolution and can be overwritten. It does not reliably tell when triage first completed. |
| `alerts.duplicates`, `alerts.false_positive_rate` | Current outcome on alerts created in range. Count each `CLOSED_DUPLICATE` alert once. For the false-positive rate, divide `CLOSED_FP` by all closed alerts excluding duplicates, matching the existing outcome denominator. Use a blank value for an empty denominator. No canonical deduplication of underlying detections. |
| `cases.recorded_resolution_time`, `cases.resolution_target_missed_count`, `cases.resolution_target_miss_rate` | One currently closed case with valid `closed_at >= created_at`, bucketed by `closed_at`. Start at creation and stop at the recorded closure. A case contributes at most once. Reopening removes it from resolved samples, even if a stale `closed_at` remains. Reclosing uses the new closure time and measures from original creation, including closed intervals. Exclude unknown or invalid timings from duration and target denominators and show coverage. |
| `cases.open_past_target`, `tasks.overdue` | Current open cases miss the target when elapsed age is strictly greater than the configured target. Closed cases miss at the same strict threshold. Open tasks are overdue when `due_date < evaluated_at`; exclude tasks with no due date. Keep open cases outside the closed miss-rate denominator. |

Parameterize target duration consistently. A dashboard can define a shared resolution target, and affected widgets reference it. The target evaluates the chosen records under the current dashboard configuration, including when an old date range is selected. It represents a reporting threshold. Persist effective policies, calendars, priority-at-start and pause/resume events before claiming historical SLA compliance.

For the future **time to first response**, start at case creation and end at the first explicit analyst acknowledgment or equivalent approved human action on the case. Automated creation in `IN_PROGRESS`, assignment, and AI recommendations alone cannot establish that action. Record actor kind and effective time. For **first completed triage**, start at alert creation and end at the first escalation or explicit terminal disposition, including duplicate closure, with the initiating action recorded. Case cascades receive a separate cause and should not automatically imply an analyst triaged the alert. Measure a reopened case's next response or resolution in an explicitly named episode metric, keyed by case and episode, with the episode clock starting on reopen. The MVP keeps the case-grain rules above. [Triage timestamp writer](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_triage_apply_service.py#L16-L67), [manual triage and link paths](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_service.py#L460-L565), [linked alert resolution](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L674-L697), [outcome denominator](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/metrics_service.py#L604-L613)

### Counts and joins

Start from one scoped row per record. Group by a scalar such as priority, status, assignee, source or title where applicable. Use an explicit unknown group for nullable dimensions. Filter by tags through containment or `EXISTS`; if grouping by tag, deduplicate record/tag pairs and label groups as overlapping. Compute totals at the original grain. Case dashboards can filter on linked child existence using `EXISTS` or a separately pre-aggregated relation. Joining a case with two alerts and three tasks produces six joined rows. Distinct case counts alone would still leave repeated case duration samples in averages and percentiles.

The original SOC rollup joins alert source buckets to case and task buckets by time and priority, and the release service has work-grain handling for summaries. Keep cases and tasks independent of the alert source dimension in the MVP. Compute percentiles over record-level samples in each result group and rates from summed eligible numerators and denominators. Drill-down uses those same contributing rows. [Rollup join](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/db_migrations/versions/001_initial_schema.py#L569-L600), [work summary](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/metrics_service.py#L577-L615), [existing tag grouping](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/metrics_service.py#L921-L967)

## Dashboard definition and live designer

Store a dashboard row with UUID, owner, scope, title, revision and timestamps. Store the versioned definition as JSONB. Scope, owner and revision live in server-controlled columns. Ship both starters as checked-in definitions using the same format. Duplicating a starter or shared dashboard creates an independent personal copy with a new dashboard ID. Save validates the full document and replaces it atomically under an expected revision. The server assigns IDs and controls publication. Keep definitions independent of saved queue filters so a renamed or deleted filter cannot silently change a chart.

Example definition for two widgets on a custom Triage Queue Health copy.

```json
{
  "schema_version": 1,
  "date": { "preset": "last_7_days" },
  "widgets": [
    {
      "id": "alert-intake",
      "title": "Critical alert intake",
      "measure": "alerts.received",
      "display": "trend",
      "group_by": "day",
      "filters": [
        { "field": "priority", "op": "in", "value": ["CRITICAL"] }
      ],
      "layout": { "order": 0, "width": "wide" }
    },
    {
      "id": "ageing-alerts",
      "title": "Awaiting triage over 24h",
      "measure": "alerts.awaiting_triage",
      "display": "number",
      "parameters": { "min_age_minutes": 1440 },
      "layout": { "order": 1, "width": "half" }
    }
  ]
}
```

The Case Response Performance starter uses the same model. A target change updates each widget that references the shared parameter.

```json
{
  "schema_version": 1,
  "date": { "preset": "last_30_days" },
  "parameters": { "resolution_target_minutes": 1440 },
  "widgets": [
    {
      "id": "resolution-misses",
      "title": "Target misses by priority",
      "measure": "cases.resolution_target_miss_rate",
      "display": "breakdown",
      "group_by": "priority",
      "parameters": {
        "target_minutes": { "dashboard_parameter": "resolution_target_minutes" }
      },
      "layout": { "order": 0, "width": "half" }
    },
    {
      "id": "follow-up",
      "title": "Overdue follow-up tasks",
      "measure": "tasks.overdue",
      "display": "table",
      "table": {
        "columns": ["human_id", "title", "due_date", "assignee", "case"],
        "sort": { "field": "due_date", "direction": "asc" }
      },
      "layout": { "order": 1, "width": "half" }
    }
  ]
}
```

For v1, the measure implies the entity and date basis. The optional grouping comes from the selected measure's catalog entry. Number requires no grouping, Trend requires a time grain, Breakdown requires a categorical dimension, and Table uses grouped summaries when a dimension is set and paginated records otherwise. A duration widget can set `aggregation` to `p50`, `mean` or `p95`, with a default supplied by the catalog. The server accepts only supported field/operator/value combinations, enum values, aggregations, units, date presets or explicit ranges, and table columns and sorts. The target widgets use a typed dashboard parameter such as `resolution_target_minutes`, referenced by a catalog-approved binding. Require unique widget IDs, deterministic order and bounds on widget count, range, groups and filter operands. Resolve parameter references to typed literal values before evaluation, with no expression evaluation. A version migration runs server-side before a definition is edited or saved. Reject unknown keys and unsupported versions with errors tied to the affected widget. Use a typed Pydantic contract, export JSON Schema for the definition and regenerate the frontend client from OpenAPI. The frontend maps the four display IDs to existing React components. The backend compiles approved identifiers to parameterized queries. The definition contains configuration and presentation options only.

### Editing flow

1. **Edit** opens an in-place canvas with a shared date control, widget action menus and a properties panel for the selection. **Add widget** opens a measure picker organized by entity, with a one-line definition and date basis. Default to a supported display and update the valid grouping and filters as choices change.
2. Valid changes preview on the canvas using viewer-scoped queries. Debounce edits, cancel superseded requests, and show errors beside the conflicting choice. Each widget keeps its last successful result during refresh with a visible updating or stale state. A preview click opens the same records as a saved result.
3. Reorder with drag handles and keyboard-accessible move controls. Choose half or full width, duplicate or remove widgets, and preview the dashboard outside edit mode before saving. Keep unfinished edits in the current session as a draft. **Save** updates the current revision, **Cancel** discards the draft, and navigation warns when leaving with unsaved edits. A revision conflict preserves local edits and offers reload or save as a personal copy.
4. The date control applies to all range-based metrics using their declared date basis. Use viewer timezone for displayed day boundaries and resolve ranges to half-open UTC intervals. Current widgets show their own as-of time and use the live queue. **Refresh** evaluates all active widgets together. Show last successful evaluation, data-through time when different, partial failures and retry. Keep temporary date overrides local to the viewer; only an explicit edit changes the saved default.

Use the existing Reports date picker, card and chart primitives, app layout and timezone context. Reuse the queue list and detail navigation for **View records**, including a return to the dashboard and its draft. MVP authors work through visual controls. The JSON serves as the persisted model and a testable contract for future controlled import/export. [Reports components](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/frontend/src/pages/Reports.tsx#L3-L23), [signed-in routes](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/frontend/src/routes/routePages.ts#L18-L33), [frontend UX conventions](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/frontend/AGENTS.md)

## Query execution, sharing and drill-down

- For the browser MVP, use authenticated session access with existing CSRF protections. Add a dashboard catalog, CRUD, batch evaluation and paginated record query under the existing FastAPI API. Keep evaluation and record selection in the same service. Supporting API keys later requires an explicit read/write scope decision for POST evaluation, because the current auth dependency derives the required key scope from the HTTP method. [Auth and API key scopes](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/admin_auth.py#L266-L318), [CSRF middleware](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/main.py#L263-L266)
- Analyst and admin can save personal dashboards. Auditors can view authorized shared dashboards and records. Reuse the current deployment-wide organization scope as the MVP meaning of team sharing. Give admins publication and shared editing rights and audit share, edit and delete actions. The UI exposes the audience before publishing. Selective team membership and manager-specific grants require a separate sharing model. Use role checks on every CRUD, preview, evaluation and drill-down request; the catalog excludes admin-only analyst performance measures for other viewers. [Auth role checks](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/admin_auth.py#L526-L630), [organization saved-filter APIs](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/api/routes/saved_filters.py#L40-L98)
- Resolve the viewer's authorized record scope before any grouping, count, sample size, value picker or related-record filter. Sharing grants the dashboard definition only. Evaluate as the viewer, and apply the same scope when a link is followed or pasted. Filter option metadata must respect the same visibility. Recheck authorization on each request, including for expired sessions and previously generated drill links.
- Each result carries a short-lived, opaque drill reference bound to the viewer and the evaluated request, including absolute date bounds, widget predicates, group or bucket, target, evaluation time and the applicable dashboard revision or draft. The server creates references for all chart points and aggregate rows. It resolves them to an exact queue URL only when the filters and boundaries match; otherwise it returns paginated record rows using the same scoped predicate. An exact title group, `triaged_at` or `closed_at` bucket, or target miss needs that latter path. Show IDs, relevant timestamps or computed durations, and links into existing record pages. Current data may change after evaluation. Keep the original filter and time anchor, show the current matching count if it differs and allow refresh.
- Evaluate bounded batches with a shared query timestamp and consistent read snapshot. Start with direct indexed record queries, predictable pagination and top-N groups with a visible truncation state. Cap expensive queries, debounce draft previews and load slower widgets independently in the UI. If caching becomes necessary, key by normalized query and viewer authorization, and invalidate correctly when access changes. Distinguish a successful zero from missing data, unsupported history or query failure.

## Historical coverage and additional capture

| Question | What can be shown |
| --- | --- |
| How much arrived each day? | Count surviving alerts, cases and tasks by creation time. Trends by title, source, priority or assignee use the current dimensions unless event-time values are captured. Complete intake after deletion requires retained creation facts and an explicit deletion policy. |
| How long did stored completions take? | Recorded alert triage and current case closure timestamps support the labeled trends above. Edits, overrides and reopens can move or remove historical points. Task `updated_at` changes for unrelated edits, so it cannot stand in for completion. |
| Which cases changed state or reopened? | Replay structured `case.status_changed` old/new values in timestamp and audit-ID order when the available stream establishes a starting state and subsequent transitions. This can recover recorded case close/reopen cohorts and intervals for verified coverage. Case audit write times describe when changes were recorded and must be distinguished from authorized imported effective timestamps. Cases created from alerts can start in progress through a different creation path. Verify initial state, imported data and event continuity before advertising coverage. [Audit schema](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/models/models.py#L1462-L1500), [case audit writer](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L1008-L1034), [escalated case creation](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_triage_apply_service.py#L70-L99) |
| What did yesterday's queue look like? | Alert/task patches, bulk audit diffs and case cascade notes provide partial evidence. There are also manual triage/link paths that stamp rows and emit realtime updates without writing equivalent structured transition facts. Current-state materialized views refresh in place. Complete as-of queues need a baseline plus full transition history, or prospective per-record snapshots. Publish the coverage start and leave earlier gaps explicit. [Manual paths](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_service.py#L460-L565), [bulk audit](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/alert_service.py#L1046-L1080), [task status update](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/task_service.py#L388-L423), [child cascade](https://github.com/tidemark-security/intercept/blob/d2ecd82c5aa0c852127ddab867150083ea1ec23d/backend/app/services/case_service.py#L437-L509) |
| Which rule version drove workload, which alerts were duplicates of the same detection, or what was the SLA at the time? | Add ingestion-time rule identity and optional version with a source namespace, explicit duplicate relationships if incident-level deduplication is needed, and effective target policy facts for SLA reporting. Use unknown for unmapped history. |

For trustworthy future timing, write typed creation, status, triage, acknowledgment and link events in the same transaction as mutations. Include entity ID, prior/next values where meaningful, actor kind, cause, effective and recorded times, and idempotent event identity. Cover REST updates, bulk actions, recommendation application, automatic case cascades and migration imports. Backfill only verified transitions and retain provenance. If backlog trends need faster queries, project per-record intervals or snapshots keyed for replay and drill-down. An aggregate-only snapshot cannot provide the underlying record set. Apply the current viewer's access and existing deletion policy to historical drill-down.

## Implementation sequence and acceptance

1. **Define record-level measures and prove parity with drill-down.** Implement the catalog and scoped base relations first. Verify status sets, migration overrides, UTC bounds and timezone buckets, null handling, numerator and denominator, overdue logic, and edge cases with reopened cases, cascaded closure, duplicate alerts and many-child joins. Test exact source, title and age predicates against result records. Benchmark representative data, then add reviewed Alembic indexes where query plans justify them.
2. **Ship the MVP.** Add the versioned definition and revisioned persistence, seed both starters, integrate the dashboard index and live designer, and wire personal ownership and admin publishing. Add visible refresh states, zero and empty states, and exact record drill-down. Regenerate frontend API types and test owner, peer, admin and auditor access across view, preview, write and drill paths. Confirm that double saves or competing edits produce one coherent revision. Exercise both starters through normal browser navigation.
3. **Add measured history.** Verify audit coverage, introduce typed events and stable ingestion identity, and expose event-based timers and backlog timelines from the earliest defensible date. Add SLA policy history and selective team membership only with their supporting data model. Profile before adding projections or snapshots.

**MVP acceptance.** Start on Dashboards as a senior analyst and allow three minutes. Duplicate Triage Queue Health, switch the intake trend to a title breakdown and filter to Critical and the chosen source to answer “Which alert titles drove critical workload from this source over the last seven days?”, then save the personal copy. Click an exact title bucket, verify its displayed count against the paginated matching records and open an alert. The analyst can complete this inside Intercept without exporting data. Separately, a manager changes the case target, opens a missed-case row, and an auditor viewing the shared copy can inspect permitted records while editing stays disabled. Use sample data with a reopened case, a late closed case, an old open alert, a duplicate closure and an overdue standalone task so the test exercises the labels and record predicates.
