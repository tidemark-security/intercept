# Link Templates - Database Storage Implementation

## Overview

Link templates are now stored in the PostgreSQL database instead of hardcoded in the frontend. This allows per-organization customization without code changes.

## Database Schema

**Table**: `link_templates`

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| template_id | String(100) | Unique identifier (e.g., 'virustotal-domain') |
| name | String(200) | Human-readable name |
| icon_name | String(100) | Icon identifier (e.g., 'Mail') |
| tooltip_template | String | Tooltip with {{variable}} placeholders |
| url_template | String | URL with {{variable}} placeholders |
| field_names | JSON | Array of field names this applies to |
| conditions | JSON | Object of field/value pairs that must match |
| enabled | Boolean | Whether template is active |
| display_order | Integer | Sort order for display |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Last update timestamp |

## Setup Instructions

### 1. Run Migration

```bash
cd backend
conda activate intercept
alembic upgrade head
```

This creates the `link_templates` table.

### 2. Seed Default Templates

```bash
python scripts/seed_link_templates.py
```

This populates the database with 10 default templates:
- ✅ Email (enabled)
- ✅ Phone (enabled)
- ✅ MS Teams Chat (enabled)
- ✅ MS Teams Call (enabled)
- ⚠️ Slack DM (disabled - needs configuration)
- ⚠️ CMDB Lookup (disabled - needs configuration)
- ⚠️ User Directory (disabled - needs configuration)
- ⚠️ Threat Intel (disabled - needs configuration)
- ✅ VirusTotal Domain (enabled)
- ✅ VirusTotal IP (enabled)

**Note**: Templates requiring organization-specific URLs are disabled by default.

### 3. Customize Templates

You can customize templates in two ways:

**Option A: Direct Database Updates**
```sql
-- Enable a template
UPDATE link_templates 
SET enabled = true, url_template = 'https://your-cmdb.com/asset/{{cmdb_id}}'
WHERE template_id = 'cmdb-lookup';

-- Add a new template
INSERT INTO link_templates (
    template_id, name, icon_name, tooltip_template, url_template,
    field_names, conditions, enabled, display_order,
    created_at, updated_at
) VALUES (
    'jira-ticket',
    'Open in Jira',
    'ExternalLink',
    'View ticket {{ticket_id}}',
    'https://your-company.atlassian.net/browse/{{ticket_id}}',
    '["ticket_id"]'::json,
    NULL,
    true,
    110,
    NOW(),
    NOW()
);
```

**Option B: Admin UI** (Coming later)
Future enhancement will provide a web interface for template management.

## API Usage

### Get All Enabled Templates

```bash
GET /api/v1/link-templates
```

Response:
```json
[
  {
    "id": 1,
    "template_id": "email",
    "name": "Email",
    "icon_name": "Mail",
    "tooltip_template": "Email {{contact_email}}",
    "url_template": "mailto:{{contact_email}}",
    "field_names": ["contact_email", "email"],
    "conditions": null,
    "enabled": true,
    "display_order": 10,
    "created_at": "2025-11-08T21:30:00Z",
    "updated_at": "2025-11-08T21:30:00Z"
  }
]
```

### Get All Templates (Including Disabled)

```bash
GET /api/v1/link-templates?enabled_only=false
```

### Get Specific Template

```bash
GET /api/v1/link-templates/{id}
```

## Frontend Integration

The frontend will need to be updated to:

1. **Fetch templates from API** instead of using hardcoded `LINK_TEMPLATES`
2. **Map icon names to React components**:
   ```typescript
   const ICON_MAP: Record<string, React.ReactNode> = {
     'Mail': <Mail />,
     'Phone': <Phone />,
     'VirusTotalIcon': <VirusTotalIcon />,
     // ... etc
   };
   ```
3. **Cache templates** in React context or localStorage for performance
4. **Parse JSON fields** (field_names, conditions) from strings

Example frontend code:
```typescript
// Fetch templates on app load
const { data: templates } = useQuery('link-templates', async () => {
  const response = await fetch('/api/v1/link-templates');
  return response.json();
});

// Convert to frontend format
const linkTemplates = templates.map(t => ({
  id: t.template_id,
  icon: ICON_MAP[t.icon_name],
  tooltip: t.tooltip_template,
  urlTemplate: t.url_template,
  fieldNames: t.field_names,  // Already a native array from API
  conditions: t.conditions,    // Already a native object/null from API
}));
```

## Migration Path

The existing `frontend/src/utils/linkTemplates.tsx` can remain as:
1. **Fallback** if API is unavailable
2. **Reference** for icon mappings
3. **Type definitions** (keep the `LinkTemplate` interface)

Eventually, it can be refactored to just handle rendering and interpolation, with data coming from the API.

## Future Enhancements

- [ ] Admin UI for template management
- [ ] Multi-tenancy support (organization_id column)
- [ ] Template versioning/audit history
- [ ] Template categories/grouping
- [ ] Variable validation (ensure required fields exist)
- [ ] Template testing/preview functionality
