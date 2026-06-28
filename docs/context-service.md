# Context Service

The Context Service stores analyst-authored notes that can be supplied to workflows when optional matching criteria apply. It replaced the earlier AI-triage-specific context feature so context can be reused outside alert triage.

AI alert triage is currently the first consumer. When an alert triage task starts, the backend finds active context entries whose criteria match the alert, stores that matched snapshot on the queued triage recommendation, and passes the same JSON into LangFlow as `triage_context_entries`. That LangFlow input name is intentionally still AI-triage-specific because it is the adapter boundary for the existing alert triage flow.

## Data Model

Context entries are persisted in `context_entries` and exposed through `ContextEntry` models.

| Field | Notes |
| --- | --- |
| `id` | Database primary key. |
| `criteria` | JSON array of `{ type, value }` objects. Empty array means the entry applies globally. |
| `body` | Analyst-authored context text. Trimmed and required. Max API payload length is 4000 characters. |
| `author` | Username that created the entry. |
| `created_at` / `updated_at` | Entry timestamps. |
| `expires_at` | Required future expiry. Naive datetimes are treated as UTC by the service. |
| `expired_at` | Set when an entry is manually expired. |

The migration creates an active-entry index on `expires_at` and `expired_at`. There are no scope-specific indexes because criteria live in JSON and matching currently happens in service code after active entries are fetched.

## Matching Rules

Every entry is global by default. Adding criteria narrows where it applies.

An active entry matches an alert when all criteria on the entry match at least one candidate extracted from the alert. This is AND logic across criteria. Multiple candidates for the same type are OR logic within that type.

Entries are returned sorted by number of criteria, then entry id. This places broadly applicable entries before more specific ones while keeping deterministic output.

## Criterion Types

Supported criterion types are `ALERT_SOURCE`, `ACTOR`, `SYSTEM`, `OBSERVABLE`, and `TAG`.

| Type | Candidate source |
| --- | --- |
| `ALERT_SOURCE` | `alert.source`. |
| `TAG` | Values from `alert.tags`. |
| `OBSERVABLE` | Typed `observable` timeline items using `observable_value` and `value`, plus legacy observable-like timeline keys. |
| `SYSTEM` | Typed `system` timeline items using `hostname`, `name`, `fqdn`, IP, asset, device, and system-name fields, plus legacy host/system-like timeline keys. |
| `ACTOR` | Typed actor timeline items only: `internal_actor`, `external_actor`, and `threat_actor`. Candidate fields include `actor_id`, `user_id`, `username`, `name`, `tag_id`, org/organization, email/contact_email, and `upn`. |

`CASE`, `USER_ACCOUNT`, `HOST_SYSTEM`, and `GLOBAL` were removed. Case-specific context should be entered as a case note. `ACTOR` does not match `alert.assignee`; it only matches timeline actor items.

## Wildcards

Criterion values support simple, case-insensitive wildcard matching.

| Pattern | Meaning |
| --- | --- |
| `*` | Matches any number of characters. |
| `?` | Matches exactly one character. |
| no wildcard | Exact case-insensitive full-value match. |

Patterns always match the full candidate value, not a substring. For example, `edr-*` matches `EDR-Primary`, but `edr` does not match `my-edr-source`.

The implementation escapes all user-provided characters except `*` and `?`, then uses a full-match regex internally. Regex syntax is not exposed to users.

Examples:

| Criterion | Matches |
| --- | --- |
| `ALERT_SOURCE = edr-*` | `EDR-Primary`, `edr-secondary` |
| `SYSTEM = *.corp.local` | `wkstn-7.corp.local` |
| `SYSTEM = wkstn-?.corp.local` | `wkstn-7.corp.local` |
| `ACTOR = ALICE.*` | `alice.admin` |
| `TAG = credential-*` | `credential-access` |

## API

Entries are managed from `/context-entries` in the frontend and `/api/v1/context-entries` in the backend.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/context-entries` | Lists active entries. Add `?include_expired=true` to include expired entries. |
| `POST` | `/api/v1/context-entries` | Creates an entry. Requires a non-auditor user. |
| `PUT` | `/api/v1/context-entries/{entry_id}` | Updates criteria, body, or expiry. Requires a non-auditor user. |
| `POST` | `/api/v1/context-entries/{entry_id}/expire` | Immediately expires an entry. Requires a non-auditor user. |

Create/update payloads use `criteria` as an optional list. Missing or empty criteria means the entry applies globally.

```json
{
  "criteria": [
    { "type": "ALERT_SOURCE", "value": "edr-*" },
    { "type": "TAG", "value": "credential-*" }
  ],
  "body": "Compare against this week's tuning exception list.",
  "expires_at": "2026-06-15T00:00:00Z"
}
```

Read responses always return `criteria` as an array.

```json
{
  "id": 12,
  "criteria": [],
  "body": "Global context for current response window.",
  "author": "analyst1",
  "created_at": "2026-06-08T00:00:00Z",
  "updated_at": "2026-06-08T00:00:00Z",
  "expires_at": "2026-06-15T00:00:00Z",
  "expired_at": null
}
```

## Audit Events

Context changes write audit log rows with entity type `context_entry`.

| Event type | Description |
| --- | --- |
| `context_entry.created` | Entry was created. |
| `context_entry.updated` | Entry criteria, body, or expiry changed. |
| `context_entry.expired` | Entry was manually expired. |

Audit snapshots use the public read shape, including `criteria`.

## Current Consumer: AI Triage

`ContextService.get_matching_context_for_alert(alert_id)` is used by the alert triage background task. Matching entries are serialized as snapshots containing `id`, `criteria`, `body`, `author`, `created_at`, `updated_at`, and `expires_at`.

The triage task writes those snapshots to `TriageRecommendation.applied_context_entries` and passes them to LangFlow under `triage_context_entries`. Keeping this field name preserves the existing AI triage flow contract while the service itself remains generic.

## MCP get_summary Consumer

`get_summary` returns active context entries that match an alert under the top-level `context` section:

```json
{
  "context": {
    "items": [
      {
        "id": 12,
        "criteria": [{ "type": "ALERT_SOURCE", "value": "edr-*" }],
        "body": "Network team is testing this detection today.",
        "author": "analyst1",
        "created_at": "2026-06-08T00:00:00Z",
        "updated_at": "2026-06-08T00:00:00Z",
        "expires_at": "2026-06-15T00:00:00Z"
      }
    ],
    "total_count": 1,
    "omitted_count": 0
  }
}
```

For `case` and `task` summaries, `context.items` is empty and both counts are `0`. Alert context entries are bounded by the existing `max_timeline_items` request limit so large temporary-context sets cannot dominate the LLM payload.
