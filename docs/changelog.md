# Changelog

## v0.5.0 - 2026-06-28

This release moves Intercept from the v0.4.x security-hardening line into a broader analyst-workflow release. It introduces case runbooks, shared context entries, richer link-template management, ServiceNow enrichment, stronger upload handling, improved search and filtering, and a larger CI/release pipeline.

### Major Changes

- Added Case Runbooks as a first-class workflow surface. Admins can create, edit, publish, disable, delete, search, and apply reusable runbooks, with PICERL-staged task definitions, task ordering, runbook task overrides, source-runbook tracking on tasks, MCP search/get tools, and triage recommendations that can suggest a runbook.
- Added analyst-authored Context Entries. Analysts can define expiring contextual guidance matched by alert source, actor, system, observable, or tag; matching context is returned on entity payloads and supplied to AI triage.
- Reworked link-template management. Public templates now support import/export, resolution endpoints, surface scoping, entity scoping, stricter URL/icon validation, and a consolidated admin UI. Personal link templates add user-owned deep links in profile management.
- Added ServiceNow enrichment. Admins can configure and preview ServiceNow user and CMDB enrichment, run cache and sync operations, render ServiceNow enrichment blocks in timelines, and use ServiceNow data for privileged actor/system context.
- Added cross-case observable enrichment to surface related observables across cases.
- Expanded alert workflows with bulk status updates, bulk case linking, bulk case creation, duplicate closure targeting, tag addition, bulk assignment, and linked-alert resolution when closing cases.
- Improved search and work queues with global search events, richer result metadata, tag match details, include/exclude tag filters, assignee filters, time filters, status groups, sorting controls, and "my open work" views on the home page.
- Improved timeline and entity UI with linked entity cards, inline linked-task editing, highlighted notes, timeline filter polish, graph/timeline refinements, PICERL stage rendering, closure summaries, duplicate target selection, and split-pane layout improvements.
- Added email evidence upload handling, `.eml` attachment support, Windows zip MIME alias normalization, server-side Magika MIME detection, safer filename sanitization, configurable attachment MIME allow/deny lists, upload size guidance from settings, and AWS ambient storage credentials.
- Added migration-only timestamp override support for NHI accounts, allowing controlled `created_at` imports for alerts, cases, and timeline items when `migration=true`.
- Added hot-configurable worker task timeouts and richer task queue runtime behavior.
- Added sidebar badge counts, recent activity feed support, and queue sorting controls.
- Added local agent/design documentation under `.agents/`, a project `CONTEXT.md`, a case-runbook ADR, a case-runbook PRD, and implementation docs for context entries, timestamp migration overrides, ServiceNow enrichment, MCP tools, and task queues.

### Security And Access Control

- Restricted case deletion to admins.
- Restricted mutation paths for auditors and non-authorized users across case runbooks, context entries, destructive case actions, dummy data, LangFlow mutations, enrichment enqueueing, task reassignment, alert relinking, and API key creation.
- Hardened CSRF bypass behavior so API-key bypasses require a valid API key.
- Hardened authentication and account flows, including password/session handling, passkeys, account reset, OIDC validation, trusted issuer auto-linking, weak test-user seeding, and reset-token handling.
- Hardened settings secret handling and Fernet key derivation.
- Hardened URL and identifier handling for timeline links, WebSocket origins, Entra ID Graph identifiers, IPv6 checks, SQL parameters, link-template URL schemes, and MCP item lookup authorization.
- Added NHI `assignable` and `override_timestamps` flags so automation accounts can be granted narrow task-assignment or migration-import powers explicitly.

### API And Data Model

- Added `/api/v1/case-runbooks` routes for listing, creating, updating, publishing, disabling, deleting, and applying case runbooks.
- Added `/api/v1/context-entries` routes for listing, creating, updating, and expiring shared context.
- Added personal link-template routes under `/api/v1/personal-link-templates`.
- Added link-template import, export, and resolve endpoints.
- Added dashboard sidebar badge count API.
- Added alert bulk action request/response models and case linked-alert resolution models.
- Added ServiceNow configure and preview models.
- Added `ContextCriterionType`, `CaseRunbookStatus`, `PICERLStage`, `SearchTagMatch`, matched context models, runbook task models, personal link-template models, portable link-template bundles, and ServiceNow configuration models.
- Added `entity_description`, `picerl_stage`, `source_runbook`, `uploaded_by_user_id`, `upload_storage_key`, `recommended_case_runbook_id`, and `applied_context_entries` fields where relevant.
- Normalized persisted tags on API responses.
- Capped timeline reply nesting depth.

### Migrations

- Added migrations for NHI assignability, AI triage context storage, context entries, user link-template preferences, case runbooks, legacy case-template aliases, triage recommended runbooks, personal link templates, single-surface link templates, and NHI timestamp overrides.
- The active migration head is `012_nhi_override_timestamps`.
- Legacy `case_templates` deployments are bridged to `case_runbooks` through compatibility migrations.
- `user_link_template_preferences` is superseded by personal link templates during the migration chain.

### Frontend

- Added `/case-runbooks` and `/context-entries` protected routes.
- Added Case Runbooks, Context Entries, and personal/admin link-template management pages and components.
- Added ServiceNow admin settings sections, preview flows, provider status, cache controls, and timeline enrichment rendering.
- Added global search overlay behavior and tag-triggered search.
- Replaced local checkbox/toggle pieces with `@tidemark-security/ux` components where applicable.
- Added reusable toolbar, section navigation, form drawer, carousel controls, PICERL stage component, context card, triage rejection dialog, and user link-template panel components.
- Updated generated frontend API models and services for the new backend contracts.
- Updated frontend dependencies, including `@tidemark-security/ux#v0.2.1`, newer React/Vite/testing packages, and client-side Magika support.

### DevOps, CI, And Release

- Bumped the application version to `0.5.0`.
- Updated release automation so pushes to `main` that change `VERSION` create the release tag from the workflow instead of relying on local tag pushes.
- Updated `AGENTS.md` to document the new release flow and avoid manual release tags.
- Added Fast CI local tooling and a pre-push hook that can run targeted backend tests, frontend typecheck, frontend Vitest, and relevant image builds.
- Updated CI workflows to cover backend tests, frontend typecheck/tests, image builds, migration compatibility, detailed PR checks, backend audit checks, and production route smoke coverage.
- Updated development Docker compose for sibling UX package development and Vite polling.
- Updated quickstart/dev configuration for generated initial admin passwords and safer localhost-bound defaults.

### Breaking Changes And Upgrade Notes

- Frontend production nginx now listens on container port `8080`. Custom compose, Kubernetes, or proxy configurations that target container port `80` must be updated.
- Backend and worker containers now run as non-root UID `10001`. Mounted volumes and runtime write paths must be writable by that UID.
- `AUTO_SEED=true` now requires a non-default `INITIAL_ADMIN_PASSWORD` of at least 12 characters.
- Attachment presign requests now require `mime_type`; clients that omit it will fail validation.
- MCP `get_item` now requires scoped `parent_entity_type` and `parent_entity_id` inputs; legacy hint fields are rejected.
- Case deletion is now admin-only.
- `created_at` overrides are migration-gated and restricted to NHI accounts with `override_timestamps`; updates that try to modify `created_at` are rejected.
- Link templates now validate URL schemes and icon identifiers, support only one `surface_scopes` value per template, and use explicit entity scoping.
- Existing encrypted settings may need verification if the deployment used a non-Fernet `SECRET_KEY` before the HKDF derivation change.
- Development Docker workflows that use the frontend dev image now expect a valid UX package context when `UX_CONTEXT` is used.
- Release tags should no longer be created or pushed manually. Merge the version bump to `main`; `.github/workflows/release.yml` creates the `vX.Y.Z` tag from `VERSION`.

### Testing

- Added backend integration coverage for case runbooks, case-runbook MCP tools, context entries, alert bulk actions, case linked-alert resolution, timestamp overrides, dashboard badge counts, link templates, task attachments, triage recommendation acceptance, ServiceNow enrichment, entity write authorization, and CSRF API-key behavior.
- Added backend unit coverage for storage, email evidence, ServiceNow, cross-case observable enrichment, link-template resolution and migration, case-runbook validation/planning, tag filtering, worker runtime config, search, metrics, timeline behavior, triage prompt contracts, and database safety.
- Added frontend unit coverage for case runbooks, context entries, link-template management, app sidebar, entity filters, timeline rendering, unified timeline, triage recommendation cards, profile link templates, search rows, URL filters, split pane behavior, tag-filter clicks, formatting utilities, icons, and status labels.
- Added Playwright coverage for production route loading and case-runbook smoke flows.
