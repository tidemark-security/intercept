# MCP Tool Reference

## Overview

This document provides a comprehensive reference for all MCP tools available in Tidemark Intercept.

The MCP server provides **6 intentionally designed tools** (not auto-generated from API routes):

| Tool | Category | Read-Only | Description |
|------|----------|-----------|-------------|
| `get_summary` | Context | Yes | Bounded context retrieval |
| `list_work` | Discovery | Yes | List and filter work items |
| `find_related` | Discovery | Yes | Find similar/related items |
| `record_triage_decision` | Triage | No | Record AI triage recommendations |
| `add_timeline_item` | Timeline | No | Append notes to timelines |
| `get_item` | Content | Yes | Retrieve full content |

**MCP URL**: `http://localhost:8000/mcp/sse`

---

## get_summary

Get bounded context summary for an alert, case, or task.

### Annotations
- `readOnlyHint`: true

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `kind` | string | Yes | - | Entity type: `"alert"`, `"case"`, `"task"` |
| `id` | string | Yes | - | Entity ID (forgiving format: `"123"`, `"ALT-000123"`, etc.) |
| `max_timeline_items` | integer | No | 25 | Max timeline items (1-50) |
| `max_observables` | integer | No | 20 | Max observables to extract (1-50) |
| `since` | string | No | null | ISO-8601 timestamp for incremental refresh |

### Returns

```json
{
  "kind": "alert",
  "id": 123,
  "human_id": "ALT-0000123",
  "header": {
    "title": "Suspicious outbound connection",
    "status": "NEW",
    "priority": "HIGH",
    "assignee": "analyst1",
    "source": "Splunk",
    "created_at": "2026-01-12T10:30:00Z",
    "updated_at": "2026-01-12T11:00:00Z"
  },
  "timeline": {
    "items": [
      {
        "id": "tl-001",
        "type": "note",
        "timestamp": "2026-01-12T10:35:00Z",
        "author": "system",
        "preview": "Initial alert created from Splunk detection...",
        "is_truncated": false
      }
    ],
    "total_count": 15,
    "omitted_count": 0,
    "bounded_by": "max_timeline_items"
  },
  "observables": {
    "items": [
      {"type": "IP", "value": "10.0.0.1", "count": 3},
      {"type": "DOMAIN", "value": "evil.example.com", "count": 1}
    ],
    "total_count": 5,
    "omitted_count": 0
  },
  "related_counts": {
    "linked_alerts": 2,
    "linked_cases": 1,
    "linked_tasks": 0,
    "similar_alerts": 8
  },
  "resources": [
    {"label": "View in UI", "url": "/alerts/123"}
  ]
}
```

### Example

```json
{
  "name": "get_summary",
  "arguments": {
    "kind": "alert",
    "id": "ALT-0000123",
    "max_timeline_items": 50
  }
}
```

---

## list_work

List and filter alerts, cases, or tasks with pagination.

### Annotations
- `readOnlyHint`: true

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `kind` | string | Yes | - | Entity type: `"alert"`, `"case"`, `"task"` |
| `statuses` | array[string] | No | null | Filter by status (see valid values below) |
| `priorities` | array[string] | No | null | Filter by priority |
| `assignees` | array[string] | No | null | Filter by assignee usernames |
| `contains` | string | No | null | Search in title + description only |
| `time_range_start` | string | No | 7 days ago | Filter by created_at >= (ISO-8601) |
| `time_range_end` | string | No | null | Filter by created_at <= (ISO-8601) |
| `limit` | integer | No | 50 | Max items (1-50) |
| `cursor` | string | No | null | Pagination cursor from previous response |

### Valid Status Values

**Alert statuses:**
- `NEW`, `IN_PROGRESS`, `ESCALATED`
- `CLOSED_TP`, `CLOSED_BP`, `CLOSED_FP`, `CLOSED_UNRESOLVED`, `CLOSED_DUPLICATE`
- Shorthand: `CLOSED` expands to all `CLOSED_*` statuses

**Case statuses:**
- `NEW`, `IN_PROGRESS`, `CLOSED`

**Task statuses:**
- `TODO`, `IN_PROGRESS`, `DONE`

### Valid Priority Values

All entity types: `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `EXTREME`

### Returns

```json
{
  "items": [
    {
      "id": 123,
      "human_id": "ALT-0000123",
      "title": "Suspicious outbound connection",
      "status": "NEW",
      "priority": "HIGH",
      "assignee": "analyst1",
      "created_at": "2026-01-12T10:30:00Z",
      "updated_at": "2026-01-12T11:00:00Z",
      "source": "Splunk"
    }
  ],
  "next_cursor": "eyJpZCI6MTAwfQ==",
  "total_count": 150
}
```

### Example

```json
{
  "name": "list_work",
  "arguments": {
    "kind": "alert",
    "statuses": ["NEW", "IN_PROGRESS"],
    "priorities": ["HIGH", "CRITICAL"],
    "limit": 20
  }
}
```

---

## find_related

Find similar/related alerts, cases, or tasks.

### Annotations
- `readOnlyHint`: true

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `seed_kind` | string | Yes | - | Seed entity type: `"alert"`, `"case"`, `"task"` |
| `seed_id` | string | Yes | - | Seed entity ID (forgiving format) |
| `max_matches` | integer | No | 10 | Max matches (1-20) |

### Returns

```json
{
  "seed": {
    "id": 123,
    "human_id": "ALT-0000123",
    "title": "Suspicious outbound connection",
    "status": "NEW",
    "priority": "HIGH",
    "assignee": "analyst1",
    "created_at": "2026-01-12T10:30:00Z",
    "updated_at": "2026-01-12T11:00:00Z",
    "source": "Splunk"
  },
  "matches": [
    {
      "kind": "alert",
      "id": 456,
      "human_id": "ALT-0000456",
      "title": "Similar outbound connection detected",
      "status": "CLOSED_TP",
      "priority": "HIGH",
      "score": 0.85,
      "why": ["same_source_title", "shared_ip:10.0.0.1"]
    },
    {
      "kind": "case",
      "id": 789,
      "human_id": "CAS-0000789",
      "title": "C2 Investigation",
      "status": "IN_PROGRESS",
      "priority": "CRITICAL",
      "score": 0.72,
      "why": ["linked_alert", "shared_domain:evil.example.com"]
    }
  ]
}
```

### Example

```json
{
  "name": "find_related",
  "arguments": {
    "seed_kind": "alert",
    "seed_id": "ALT-0000123",
    "max_matches": 15
  }
}
```

---

## record_triage_decision

Record AI triage recommendation for an alert.

Recommendations start as `PENDING` until an analyst accepts or rejects them. A new recommendation replaces any existing one (setting the old one to `SUPERSEDED`).

### Annotations
- `readOnlyHint`: false (write operation)

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `alert_id` | string | Yes | - | Alert ID (forgiving format) |
| `disposition` | string | Yes | - | Triage outcome (see valid values) |
| `confidence` | float | Yes | - | Agent confidence (0.0-1.0) |
| `reasoning_bullets` | array[string] | No | null | Why this disposition |
| `evidence_refs` | array[string] | No | null | Timeline item IDs supporting recommendation |
| `recommended_actions` | array[object] | No | null | Suggested next steps. Each object: `{title: string, description?: string}` |
| `suggested_status` | string | No | null | Optional alert status patch |
| `suggested_priority` | string | No | null | Optional priority patch |
| `suggested_assignee` | string | No | null | Optional assignee patch (username) |
| `suggested_tags_add` | array[string] | No | null | Tags to add |
| `suggested_tags_remove` | array[string] | No | null | Tags to remove |
| `request_escalate_to_case` | boolean | No | false | Request case creation |
| `commit` | boolean | No | false | If false, returns dry-run preview only |

### Valid Disposition Values

- `TRUE_POSITIVE`
- `FALSE_POSITIVE`
- `BENIGN`
- `NEEDS_INVESTIGATION`
- `DUPLICATE`
- `UNKNOWN`

### Valid Status Values (for suggested_status)

`NEW`, `IN_PROGRESS`, `ESCALATED`, `CLOSED_TP`, `CLOSED_BP`, `CLOSED_FP`, `CLOSED_UNRESOLVED`, `CLOSED_DUPLICATE`

### Valid Priority Values (for suggested_priority)

`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `EXTREME`

### Returns

```json
{
  "mode": "dry_run",
  "recommendation_id": null,
  "suggested_patches": [
    {"field": "status", "current_value": "NEW", "new_value": "CLOSED_FP"},
    {"field": "priority", "current_value": "HIGH", "new_value": "LOW"}
  ],
  "status": "PENDING",
  "message": "Dry-run preview. Set commit=true to apply."
}
```

When `commit=true`:

```json
{
  "mode": "committed",
  "recommendation_id": 42,
  "suggested_patches": [...],
  "status": "PENDING",
  "message": "Triage recommendation recorded successfully."
}
```

### Example

```json
{
  "name": "record_triage_decision",
  "arguments": {
    "alert_id": "ALT-0000123",
    "disposition": "FALSE_POSITIVE",
    "confidence": 0.92,
    "reasoning_bullets": [
      "Source IP belongs to internal scanner",
      "Activity matches scheduled vulnerability scan"
    ],
    "suggested_status": "CLOSED_FP",
    "suggested_priority": "INFO",
    "commit": true
  }
}
```

---

## add_timeline_item

Add timeline note to an alert, case, or task.

This is an append-only operation. Idempotent via client-provided `item_id`.

### Annotations
- `readOnlyHint`: false (write operation)

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `target_kind` | string | Yes | - | Entity type: `"alert"`, `"case"`, `"task"` |
| `target_id` | string | Yes | - | Entity ID (forgiving format) |
| `item_id` | string | Yes | - | Client-provided unique ID (for idempotency) |
| `body` | string | Yes | - | Note content (max 16,000 chars) |
| `commit` | boolean | No | false | If false, returns dry-run preview only |
| `created_at` | string | No | now | ISO-8601 timestamp |

### Returns

```json
{
  "mode": "dry_run",
  "item_id": "note-abc123",
  "created_at": null,
  "author": null,
  "message": "Dry-run preview. Set commit=true to apply."
}
```

When `commit=true`:

```json
{
  "mode": "committed",
  "item_id": "note-abc123",
  "created_at": "2026-01-12T11:30:00Z",
  "author": "triage_agent",
  "message": "Timeline item added successfully."
}
```

When item already exists (idempotent):

```json
{
  "mode": "already_exists",
  "item_id": "note-abc123",
  "created_at": "2026-01-12T11:30:00Z",
  "author": "triage_agent",
  "message": "Timeline item already exists."
}
```

### Example

```json
{
  "name": "add_timeline_item",
  "arguments": {
    "target_kind": "case",
    "target_id": "CAS-0000123",
    "item_id": "agent-analysis-20260112-001",
    "body": "## Automated Analysis\n\nReviewed 15 related alerts. Key findings:\n- Common IOC: 10.0.0.1\n- Pattern suggests lateral movement\n- Recommend immediate containment",
    "commit": true
  }
}
```

---

## get_item

Get full content of a truncated timeline item.

Supports pagination for very large items.

### Annotations
- `readOnlyHint`: true

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `item_id` | string | Yes | - | Timeline item ID |
| `mode` | string | No | `"full"` | Retrieval mode: `"full"`, `"head"`, `"tail"` |
| `max_chars` | integer | No | 4000 | Max characters (100-10000) |
| `cursor` | string | No | null | Pagination cursor from previous response |
| `hint_kind` | string | No | null | Optional entity type hint for faster lookup |
| `hint_parent_id` | string | No | null | Optional parent entity ID hint |

### Returns

```json
{
  "item_id": "tl-001",
  "content": "Full content of the timeline item...",
  "metadata": {
    "type": "note",
    "timestamp": "2026-01-12T10:35:00Z",
    "author": "analyst1",
    "parent_kind": "alert",
    "parent_id": 123,
    "parent_human_id": "ALT-0000123"
  },
  "next_cursor": null,
  "is_truncated": false
}
```

### Example

```json
{
  "name": "get_item",
  "arguments": {
    "item_id": "tl-001",
    "mode": "full",
    "max_chars": 8000
  }
}
```

---

## ID Format Reference

All tools accept **forgiving ID formats**:

| Entity | Prefix | Examples |
|--------|--------|----------|
| Alert | `ALT-` | `123`, `ALT-123`, `ALT-0000123` |
| Case | `CAS-` | `456`, `CAS-456`, `CAS-0000456` |
| Task | `TSK-` | `789`, `TSK-789`, `TSK-0000789` |

The server normalizes all formats internally, so use whichever is most convenient.

---

## Error Responses

### 401 Unauthorized

```json
{"message": "API key required. Use Authorization: Bearer <key> or X-API-Key header."}
```

```json
{"message": "Invalid API key"}
```

```json
{"message": "API key has expired"}
```

```json
{"message": "API key has been revoked"}
```

### 403 Forbidden

```json
{"message": "User account is not active"}
```

### 404 Not Found

Returned when the requested entity (alert, case, task, timeline item) does not exist.

### 422 Validation Error

Returned when parameters fail validation (e.g., invalid `kind`, out-of-range `limit`).

---

## Next Steps

- See [Integration Guide](./integration-guide.md) for usage patterns
- Read [Configuration Guide](./configuration.md) for deployment options
