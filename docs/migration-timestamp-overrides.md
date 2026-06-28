# Migration Timestamp Overrides

Intercept normally owns creation timestamps. API consumers cannot set `created_at`
on alerts, cases, tasks, or timeline items during ordinary writes. This keeps
audit trails, realtime events, queueing, and user activity anchored to server
time.

The one supported exception is data migration from another case management
system. Migration imports may backdate creation timestamps, but only through an
explicit NHI-only capability.

## Capability Model

Timestamp override access is controlled by the `override_timestamps` flag on
`user_accounts`.

- The flag defaults to `false`.
- The flag is intended only for NHI accounts.
- Human users and auditors cannot use migration timestamp override mode.
- Admins provision a migration NHI, enable `Override timestamps`, and use that
  NHI's API key for the import.

The Admin Users screen shows `Override timestamps` only when creating or editing
an NHI account. The flag is near the existing `Assignable AI task agent`
capability.

## API Contract

The following create endpoints accept a `migration` query parameter:

| Endpoint | Backdated field |
| --- | --- |
| `POST /api/v1/alerts?migration=true` | Alert `created_at` |
| `POST /api/v1/cases?migration=true` | Case `created_at` |
| `POST /api/v1/tasks?migration=true` | Task `created_at` |
| `POST /api/v1/alerts/{id}/timeline?migration=true` | Timeline item `created_at` |
| `POST /api/v1/cases/{id}/timeline?migration=true` | Timeline item `created_at` |
| `POST /api/v1/tasks/{id}/timeline?migration=true` | Timeline item `created_at` |

`created_at` is honored only when all of these are true:

- `created_at` is supplied in the request body.
- `migration=true` is supplied in the query string.
- The caller is authenticated as an NHI account.
- That NHI account has `override_timestamps=true`.
- The timestamp includes timezone information.

Accepted timestamps are normalized to UTC before storage.

## Error Behavior

| Request | Response |
| --- | --- |
| `created_at` supplied without `migration=true` | `400 Bad Request` |
| `migration=true` used by a human user | `403 Forbidden` |
| `migration=true` used by an auditor | `403 Forbidden` |
| `migration=true` used by an NHI without `override_timestamps` | `403 Forbidden` |
| Naive `created_at`, such as `2024-01-02T03:04:05` | Validation error |
| Timeline update payload includes `created_at` | `400 Bad Request` |

Timeline item `created_at` is immutable after creation. To preserve import
lineage, clients should choose stable timeline item IDs during migration and
retry failed imports idempotently instead of editing creation metadata later.

## Preserved Server-Time Semantics

Timestamp override mode only affects the creation timestamp of the target record
or appended timeline item.

The following values remain server-time values:

- `updated_at`
- `linked_at`
- audit log timestamps
- realtime event timestamps
- queue and triage enqueue timestamps
- timeline event `timestamp`
- enrichment and worker side effects

For timeline items, `created_at` may represent the historical creation time from
the source system, while `timestamp` continues to represent the authoritative
chronology of when the event actually occured.

## Examples

Create a migration NHI:

```bash
curl -X POST http://localhost:8000/api/v1/admin/auth/users/nhi \
  -H "Content-Type: application/json" \
  -H "Cookie: intercept_session=admin-session" \
  -d '{
    "username": "case_migration_importer",
    "role": "ANALYST",
    "description": "Imports historical cases from the legacy case platform",
    "assignable": false,
    "override_timestamps": true,
    "initial_api_key_name": "Migration Import",
    "initial_api_key_expires_at": "2027-01-01T00:00:00Z"
  }'
```

Create a backdated case:

```bash
curl -X POST "http://localhost:8000/api/v1/cases?migration=true" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer int_migration_key" \
  -d '{
    "title": "Legacy phishing investigation",
    "description": "Imported from legacy case platform",
    "priority": "HIGH",
    "created_at": "2024-01-02T03:04:05+10:00"
  }'
```

Append a backdated timeline note:

```bash
curl -X POST "http://localhost:8000/api/v1/cases/123/timeline?migration=true" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer int_migration_key" \
  -d '{
    "id": "legacy-note-4815162342",
    "type": "note",
    "description": "Initial analyst notes imported from legacy system.",
    "created_at": "2024-01-02T04:15:00+10:00"
  }'
```

## MCP Imports

The MCP `add_timeline_item` tool follows the same gate. To backdate a timeline
note through MCP, pass both `migration=true` and `created_at`, authenticate with
an NHI API key, and enable `override_timestamps` on that NHI account.

```json
{
  "name": "add_timeline_item",
  "arguments": {
    "target_kind": "case",
    "target_id": "CAS-0000123",
    "item_id": "legacy-note-4815162342",
    "body": "Imported analyst note from legacy system.",
    "commit": true,
    "migration": true,
    "created_at": "2024-01-02T04:15:00+10:00"
  }
}
```
