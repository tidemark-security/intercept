# PRD: Case Runbooks

Labels: ready-for-agent

## Problem Statement

Analysts need a fast way to turn recurring incident response patterns into case work without being forced through extra prompts during alert escalation. Today, cases and tasks are first-class concepts, but there is no shared Case Runbook Library, no way for a Triage Recommendation to recommend a Case Runbook, and no case-level PICERL view that helps an incident manager see response progress by stage.

The result is duplicated manual work: analysts recreate common response tasks, AI triage can only suggest one-off Recommended Actions, and incident managers cannot quickly understand which PICERL stages have work, gaps, overdue tasks, or completed tasks.

## Solution

Build a Case Runbook feature that lets admins define reusable Case Runbooks, lets analysts and auditors inspect them in a top-level Case Runbook Library, and lets analysts apply published runbooks to live cases through a `/run` RightDock workflow. Applying a Case Runbook creates real Task entities linked to the case timeline, never ghost tasks or checklist-only items.

Triage Recommendations can recommend either a published Case Runbook or Recommended Actions when escalating to a case. If a published Case Runbook is accepted through a Triage Recommendation, Intercept applies it immediately as the fast path and navigates the analyst into the new case. Manual escalation remains frictionless and does not prompt for a runbook.

Tasks gain optional PICERL Stage metadata. Runbook Tasks require PICERL Stage. Case detail gains stage bands and a swimlane timeline mode for staged tasks, both driven by real linked tasks and existing filter behavior.

## User Stories

1. As an analyst, I want to inspect a Case Runbook Library, so that I can understand the response patterns available in Intercept.
2. As an analyst, I want the Case Runbook Library to be top-level navigation near Cases, so that I can find runbooks without going through admin settings.
3. As an analyst, I want to see published runbooks by default, so that the library shows operationally relevant runbooks first.
4. As an analyst, I want to optionally include draft runbooks in the library view, so that I can review runbooks being prepared and give feedback.
5. As an analyst, I want to optionally include disabled runbooks in the library view, so that I can understand retired response structures when needed.
6. As an auditor, I want the same read-only Case Runbook Library visibility as analysts, so that I can audit response guidance without special exceptions.
7. As an admin, I want to create Case Runbooks as drafts by default, so that unfinished runbooks are not accidentally applied to live cases.
8. As an admin, I want to edit published runbooks directly, so that I can maintain response guidance without a heavyweight versioning workflow.
9. As an admin, I want edits to Case Runbooks to be audited, so that runbook changes are reviewable later.
10. As an admin, I want to publish a draft only after validation passes, so that analysts can only apply complete runbooks.
11. As an admin, I want to disable a Case Runbook, so that it no longer appears in MCP or application flows while remaining visible in the library by filter.
12. As an admin, I want deletion to leave a redacted tombstone, so that audit and provenance records remain intact without retaining operational content.
13. As an admin, I want Case Runbook titles to be unique among non-deleted runbooks, so that analysts do not see confusing duplicate names.
14. As an admin, I want Runbook Task titles to be unique within a Case Runbook, so that application review does not show duplicate-looking work.
15. As an admin, I want to reorder Runbook Tasks, so that applying a runbook creates tasks in the intended timeline order.
16. As an admin, I want Runbook Task definitions to include title, description, PICERL Stage, optional relative due offset, optional priority, and tags, so that runbooks can define useful case work.
17. As an admin, I want runbook-level case tags, so that applying a runbook can add declared tags to the parent case.
18. As an admin, I want Runbook Tasks stored as a JSONB document under the runbook, so that editing and applying runbooks stays simple.
19. As an analyst, I want `/run` to be available only on case timelines, so that Case Runbooks cannot be applied to alerts or tasks.
20. As an analyst, I want `/run` to open a RightDock flow, so that applying a runbook feels like creating other timeline items.
21. As an analyst, I want the new-item menu to include Case Runbook on case pages, so that I can apply runbooks without memorizing slash commands.
22. As an analyst, I want the `/run` RightDock to be a single scrollable flow, so that runbook selection and task review stay simple.
23. As an analyst, I want to search and select a published Case Runbook inside `/run`, so that I can choose the right response structure.
24. As an analyst, I want all Runbook Tasks selected by default, so that applying a runbook is fast.
25. As an analyst, I want to uncheck irrelevant Runbook Tasks, so that the created case work matches the incident.
26. As an analyst, I do not want select-all/select-none controls, so that large opt-outs reveal runbook quality problems instead of becoming normal workflow.
27. As an analyst, I want to set an assignee per Runbook Task in the application flow, so that work can be distributed before task creation.
28. As an analyst, I want Runbook Tasks to be unassigned by default, so that runbook application does not falsely assign work to me.
29. As an analyst, I want relative due offsets to appear as computed due dates during application, so that I can adjust the actual due date before tasks are created.
30. As an analyst, I want to edit the computed due date rather than the runbook offset, so that the live case task is adjusted without changing the runbook.
31. As an analyst, I want duplicate warnings based on existing case task titles, so that I can avoid accidentally creating duplicate work.
32. As an analyst, I want duplicate warnings to be non-blocking, so that I can still create similar tasks when needed.
33. As an analyst, I want applying a Case Runbook to create real Task entities, so that the tasks appear in the global task list and task detail pages.
34. As an analyst, I want applying a Case Runbook to add a system audit note to the case timeline, so that the case shows what runbook was applied.
35. As an analyst, I want the audit note to include runbook ID/title, who applied it, created task count, and skipped task titles, so that application history is understandable.
36. As an analyst, I want no ghost Runbook Tasks, so that all visible task work is real case work.
37. As an analyst, I want existing manual case escalation to stay frictionless, so that I can get into case mode without selecting a runbook.
38. As an analyst, I want accepting an escalating Triage Recommendation with a Case Runbook to apply the runbook immediately, so that triage stays fast.
39. As an analyst, I want accepting an escalating Triage Recommendation to navigate to the new case, so that I can continue investigation immediately.
40. As an analyst, I want a recommended runbook that is no longer published to explain why it cannot be applied and offer a new runbook or no-runbook path, so that stale recommendations do not block case creation.
41. As an analyst, I want non-escalating recommendations to never include Case Runbooks or Recommended Actions, so that dismissal workflows do not create meaningless work.
42. As an AI agent, I want to search published Case Runbooks by text, so that I can discover candidate runbooks before recommending one.
43. As an AI agent, I want to fetch a lean Case Runbook detail payload, so that I can inspect Runbook Tasks without excessive context.
44. As an AI agent, I want to recommend either a Case Runbook or Recommended Actions, so that I can choose structured response work when available and fallback actions when not.
45. As an incident manager, I want PICERL stage bands on case timelines when staged tasks exist, so that I can see response progress quickly.
46. As an incident manager, I want stage bands to show all six PICERL stages, so that gaps are visible.
47. As an incident manager, I want stage bands to show done/total counts and warning treatment for attention-needed tasks, so that progress and risk are visible.
48. As an incident manager, I want clicking a stage band to filter to staged tasks for that stage, so that I can focus on one response stage.
49. As an incident manager, I want clicking the active stage band again to clear the filter, so that I can return to the whole timeline easily.
50. As an incident manager, I want PICERL filtering to combine with existing filters using AND semantics, so that filtering remains predictable.
51. As an incident manager, I want graph view to ghost non-matching items for PICERL filters, so that graph filtering behaves consistently.
52. As an incident manager, I want a swimlane timeline mode with PICERL stages as columns, so that I can see staged task distribution at a glance.
53. As an incident manager, I want swimlane to show only tasks with PICERL Stage, so that the swimlane stays focused on response work.
54. As an incident manager, I want swimlane to show all six stages including empty columns, so that missing stage work is visible.
55. As an incident manager, I want swimlane cards ordered by task timestamp within each stage, so that existing timeline ordering remains the source of truth.

## Implementation Decisions

- Build a Case Runbook model with lifecycle status values `DRAFT`, `PUBLISHED`, `DISABLED`, and `DELETED`.
- New Case Runbooks default to `DRAFT`.
- Only `PUBLISHED` Case Runbooks are applicable to live cases, visible to MCP runbook tools, and valid for Triage Recommendations.
- Drafts can never be applied to a live case by anyone.
- The Case Runbook Library is top-level navigation. Analysts, auditors, and admins can inspect runbooks read-only.
- The Case Runbook Library defaults to `PUBLISHED`. Analysts and auditors may opt in to `DRAFT` and `DISABLED`. `DELETED` is admin/tombstone state and is not part of the normal non-admin library.
- Editing, creating, publishing, disabling, and deleting Case Runbooks requires admin permission.
- Template deletion redacts content and sets status to `DELETED`. Keep identifiers and audit ownership/timestamps. Set title and description to null and clear case tags and Runbook Tasks.
- Case Runbook titles are required for `DRAFT`, `PUBLISHED`, and `DISABLED`; nullable only for `DELETED`.
- Case Runbook titles are unique among non-deleted runbooks using case-insensitive, whitespace-normalized comparison.
- Case Runbook descriptions support Markdown and are required for `PUBLISHED`.
- Case Runbook descriptions describe the runbook, not a suggested case description.
- Case Runbooks do not contain or mutate case title, case description, case priority, case status, or case assignee.
- Case Runbook root data includes ID, human ID, title, description, lifecycle status, case tags, Runbook Tasks, created/updated timestamps, and created/updated users.
- Case Runbook identifiers follow existing entity ID conventions: integer canonical ID plus `RUN-0000001` human presentation and forgiving parsing.
- Case tags are a runbook-level JSONB column.
- Runbook Tasks are stored as a JSONB document under the Case Runbook, per ADR 0001.
- Full API responses are assembled from relational runbook columns plus `runbook_tasks`; do not duplicate ID/title/description inside the JSONB task document.
- Runbook Task fields are title, optional description, PICERL Stage, optional Relative Due Date Offset in seconds, optional priority, and tags.
- Runbook Task descriptions support Markdown.
- Published Runbook Tasks require title and PICERL Stage.
- Published Case Runbooks require at least one Runbook Task.
- Runbook Task titles must be unique across the whole Case Runbook using case-insensitive, whitespace-normalized comparison.
- Runbook Task priority is optional. When omitted, the created Task inherits the parent Case priority.
- Relative Due Date Offset is stored as seconds and converted into an absolute due date when applying a runbook.
- Manual application edits computed task due dates, not runbook offsets.
- Runbook Task tags are applied exactly as defined, aside from existing backend tag normalization or dedupe behavior.
- Template dependencies are out of schema in v1. Dependencies may be implied by recorded task order or written into descriptions.
- Applying a Case Runbook requires at least one selected Runbook Task. There is no tag-only application path.
- Applying a Case Runbook creates real Task entities linked to the case and rendered through existing TaskItem timeline behavior.
- Runbook-created tasks get `source_runbook`, linking to the Case Runbook ID only.
- Do not store provenance to specific Runbook Task indexes or task definitions.
- Applying a Case Runbook adds a system audit note on the case timeline. The note includes Case Runbook ID/title, applier, created task count, and skipped Runbook Task titles.
- Applying a Case Runbook adds declared case tags to the parent case.
- Applying a Case Runbook preserves runbook order by creating tasks with sequential timestamps.
- Applying the same Case Runbook more than once is allowed. The UI should warn when prior application or existing `source_runbook`/task-title evidence suggests duplication.
- Manual application uses the existing RightDock pattern. `/run` and the new-item menu option are case-only and never appear on alert or task pages.
- `/run` is a single scrollable RightDock flow: search/select runbook at the top; review task rows below.
- No select-all/select-none control in `/run`.
- No final summary section before Apply in `/run`.
- Each task review row shows PICERL Stage, selected checkbox, title, description, computed due date, assignee picker, duplicate warning, priority, and tags as read-only where applicable.
- Manual `/run` application lets analysts specify assignee per selected task with the normal assignee picker.
- Runbook-created tasks are unassigned by default when no assignee is specified, including recommendation acceptance.
- MCP adds `search_case_runbooks` with `query` and `limit`. It searches published runbook title/description and Runbook Task title/description, returns published operational summaries only, and defaults to title order when query is empty.
- MCP adds `get_case_runbook`, which returns only published runbooks and uses lean responses: ID, human ID, title, description, case tags, and Runbook Task definitions.
- MCP `record_triage_decision` gains `recommended_case_runbook_id`, accepting integer or forgiving `RUN-` human ID and storing the integer.
- `recommended_case_runbook_id` and `recommended_actions` are mutually exclusive and reject-on-write if both are provided.
- `recommended_case_runbook_id` requires `request_escalate_to_case = true`.
- `recommended_actions` also require `request_escalate_to_case = true`, fixing the current bug where dismissal recommendations can carry follow-up tasks.
- If `request_escalate_to_case = true`, `suggested_status` must be null/omitted or `ESCALATED`.
- Non-escalating recommendations can suggest disposition, reasoning, status/priority/assignee/tags, but not Case Runbooks or Recommended Actions.
- Triage Recommendations store only the Case Runbook integer ID, not a title/description snapshot.
- Accepting a recommendation with a published Case Runbook creates the case, applies the runbook immediately without a modal, creates all Runbook Tasks, adds case tags and audit note, and navigates to the new case.
- If a pending recommendation references a runbook that is no longer published, acceptance pauses and explains the runbook is unavailable. For escalation recommendations, the analyst can choose another published runbook or continue without a runbook.
- Case Runbook management changes emit audit log entries with `entity_type = "case_runbook"` and event types `case_runbook.created`, `case_runbook.updated`, `case_runbook.deleted`, `case_runbook.published`, and `case_runbook.disabled` or equivalent lifecycle terminology.
- Task gains optional PICERL Stage metadata. PICERL Stage is required for Runbook Tasks and optional for manual tasks.
- PICERL Stage is a fixed enum: Preparation, Identification, Containment, Eradication, Recovery, Lessons Learned.
- PICERL Stage appears on the task entity metadata card.
- Case detail shows PICERL stage bands only when the case has at least one task with PICERL Stage.
- Stage bands are case-detail only, not task-detail.
- Stage bands show all six PICERL stages, even empty stages.
- Stage bands show done/total whole-case staged-task counts independent of active filters.
- Stage bands show warning treatment when a stage contains overdue or attention-needed tasks.
- Clicking a stage band toggles a task-only PICERL filter. Clicking again clears it.
- PICERL filtering combines with existing filters using AND semantics.
- The PICERL stage strip is separate from, but near, the existing sticky timeline filters and above the entity metadata card. Deeper filter bar integration is v2.
- In graph view, PICERL filtering ghosts non-matching items using the existing graph filtering approach.
- Add swimlane as a third timeline display mode alongside list and graph.
- Swimlane columns are the six PICERL stages. It shows only tasks with PICERL Stage, ordered by task timestamp within each column.
- In swimlane view, a selected PICERL stage highlights the selected stage and ghosts/mutes other stage columns/cards rather than removing columns.

Deep modules to build or modify:

- Case Runbook validation module: owns lifecycle validation, title normalization, Runbook Task validation, title uniqueness, and publishability checks.
- Case Runbook application planner: takes a case, a published Case Runbook, selected task overrides, and an application timestamp; returns planned task creations, duplicate warnings, due dates, case tag changes, sequential timestamps, and audit note text.
- Case Runbook service/API layer: owns management CRUD, lifecycle transitions, tombstone redaction, audit emission, search/list behavior, and apply endpoint.
- Triage Recommendation contract validator: owns escalation/runbook/action invariants and prevents invalid non-escalating work recommendations.
- MCP Case Runbook tools: owns lean runbook discovery/detail payloads and forgiving `RUN-` parsing.
- PICERL task metadata/filter module: owns stage counts, stage filtering, graph ghosting inputs, and swimlane task grouping.
- Case Runbook Library UI: owns list/detail layout, status filters, read-only analyst/auditor view, and admin edit affordances.
- `/run` RightDock application UI: owns runbook search/select, task review rows, checkbox opt-outs, assignee picker, due date override, duplicate warnings, and apply action.

## Testing Decisions

- Tests should cover externally visible behavior, not implementation details. Good tests assert API responses, persisted state, emitted audit records, visible UI behavior, and created case/task outcomes.
- Unit-test the Case Runbook validation module thoroughly:
  - Drafts can be incomplete.
  - Published runbooks require title, description, at least one Runbook Task, Runbook Task title, and PICERL Stage.
  - Non-deleted titles are unique with case-insensitive whitespace normalization.
  - Runbook Task titles are unique across the whole runbook with the same normalization.
  - Deleted tombstones allow null title and redacted content.
- Unit-test the application planner:
  - It creates no plan when no tasks are selected.
  - It computes due dates from relative seconds.
  - It preserves selected runbook order with sequential timestamps.
  - It inherits case priority when task priority is absent.
  - It respects explicit task priority.
  - It leaves tasks unassigned by default.
  - It applies per-task assignee overrides.
  - It detects title-normalized duplicate warnings without blocking.
  - It produces the expected case timeline audit note.
- API tests should cover Case Runbook management:
  - List defaults and status filtering.
  - Non-admin read access versus admin write access.
  - Create defaults to draft.
  - Publish validation.
  - Edit published runbook validation.
  - Disable/deleted behavior.
  - Delete redaction and tombstone persistence.
  - Audit log emission for create/update/publish/disable/delete.
- API tests should cover applying runbooks:
  - Only published runbooks are applicable.
  - Draft/disabled/deleted runbooks cannot be applied.
  - Applying creates real tasks linked to the case.
  - Created tasks carry `source_runbook`.
  - Case tags are added.
  - The case timeline audit note is created.
  - Sequential timestamps produce deterministic order.
- MCP tests should cover:
  - `search_case_runbooks` returns only published runbooks.
  - Search matches runbook text and Runbook Task text.
  - Empty query returns title-ordered published runbooks.
  - `get_case_runbook` returns lean published detail and rejects runbooks that are not published.
  - `record_triage_decision` accepts integer and human `RUN-` identifiers.
  - Invalid runbook/action combinations reject on write.
  - Template/action fields require `request_escalate_to_case = true`.
  - Escalating recommendations reject contradictory `suggested_status`.
- Triage Recommendation acceptance tests should cover:
  - Published runbook acceptance creates a case, tasks, case tags, and audit note.
  - Recommended Actions create tasks only on escalating recommendations.
  - Non-escalating recommendations cannot carry work fields.
  - A recommended runbook that is no longer published causes a clear intervention path instead of silently applying.
- Frontend component tests should cover:
  - Case Runbook Library default and opt-in status filters.
  - Read-only access for analysts/auditors.
  - Admin-only edit affordances.
  - `/run` visibility only on case pages.
  - `/run` task checkboxes, assignee picker, due date edits, and duplicate warning display.
  - Apply disabled when no tasks are selected.
  - Stage bands appear only when staged tasks exist.
  - Stage band counts use whole-case staged-task counts.
  - Stage band click toggles PICERL filtering.
  - PICERL filtering combines with existing filters.
  - Graph view ghosts non-matching items when PICERL filter is active.
  - Swimlane shows all six stages and only staged tasks.
- E2E smoke tests should cover the main analyst path:
  - Admin creates/publishes a runbook.
  - Analyst applies it with `/run`.
  - Tasks appear on the case timeline.
  - PICERL bands appear and filter.
  - Swimlane mode shows staged tasks.
- Prior art in the codebase includes task/case/alert service API tests, timeline item creation/update tests, task due status tests, timeline renderer tests, production route smoke tests, and existing EntityList/RightDock/UI patterns.

## Out of Scope

- Case Runbook versioning.
- Per-Runbook Task identity or provenance.
- Applying draft runbooks to live cases.
- Ghost tasks, inline recommendation tasks, or checklist-only runbook items.
- Hard delete through the UI.
- Template dependencies as schema or enforced task blocking.
- Required/non-skippable Runbook Tasks.
- Task tag editing during `/run` application.
- Select-all/select-none in the `/run` application flow.
- Final summary/confirmation step in `/run`.
- Case Runbook cloning API.
- Business-hours due date calculations.
- Contextual `recommend_case_runbook(alert_id)` MCP tool.
- Deep integration of PICERL bands into the existing filter bar; v1 uses a separate strip near the sticky filters.
- Stage metadata for non-task timeline items.
- Case Runbooks mutating core case fields.

## Further Notes

- The prototype references five UI explorations. The selected direction combines inline PICERL stage bands, RightDock-based runbook application, real task cards, and swimlane view. The ghost task concept is explicitly rejected.
- The Case Runbook Library should feel like the existing live list/detail pages, loosely following the Alerts page layout.
- The `/run` flow should reuse existing RightDock behavior, including mobile full-screen behavior.
- The assignee selector and date-time picker should reuse existing components.
- MCP responses should remain lean to avoid context rot.
- The current implementation already has explicit `request_escalate_to_case` in the MCP contract and stores it on Triage Recommendations. It also currently forces case escalation when an accepted recommendation does not close the alert; the new validation should make invalid work recommendations fail earlier.
- The current implementation has a bug: non-escalating/dismissal recommendations can include Recommended Actions today. This PRD requires rejecting those on write.
