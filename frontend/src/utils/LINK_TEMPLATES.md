# Link Template System

A configuration-driven approach for generating contextual action links from timeline items with automatic field detection.

## Overview

The link template system automatically generates appropriate action buttons based on the fields present in timeline items. Each template defines which fields it applies to, eliminating the need for manual configuration per item type.

### Core Components

1. **Link Templates** (`linkTemplates.tsx`) - Template definitions with field associations
2. **LinkButton Component** (`components/timeline/LinkButton.tsx`) - Reusable button component
3. **Link Utilities** (`components/timeline/linkUtils.tsx`) - Helper functions for generating buttons

## Quick Start

### Automatic Link Detection (Recommended)

Timeline cards automatically generate appropriate links based on fields present in the item:

```tsx
import { createTimelineCard } from '@/components/timeline/TimelineCardFactory';

// If item has contact_email -> automatically adds email button
// If item has contact_phone -> automatically adds phone button  
// If item has cmdb_id -> automatically adds CMDB lookup button
const cardProps = createTimelineCard(item, {
  size: 'large',
});

return <BaseCard {...cardProps} />;
```

### Direct Auto-Link Generation

Generate links directly without using the card factory:

```tsx
import { generateAutoLinks } from '@/utils/linkTemplates';
import { LinkButton } from '@/components/timeline/LinkButton';

const item = {
  contact_email: 'john@example.com',
  contact_phone: '+1234567890',
  cmdb_id: 'ASSET-123',
};

const links = generateAutoLinks(item);
// Returns: [email link, phone link, CMDB link]

// Render buttons
{links.map(link => (
  <LinkButton
    key={link.id}
    href={link.url}
    icon={link.icon}
    tooltip={link.tooltip}
  />
))}
```

## Link Template Configuration

### LinkTemplate Interface

```typescript
interface LinkTemplate {
  /** Unique identifier for this template */
  id: string;
  
  /** Icon component to display in the button */
  icon: React.ReactNode;
  
  /** Tooltip text (supports {{variable}} interpolation) */
  tooltip: string;
  
  /** URL template (supports {{variable}} interpolation) */
  urlTemplate: string;
  
  /** Field names that this template applies to (for automatic detection) */
  fieldNames?: string[];
  
  /** Optional: condition function to determine if link should be shown */
  condition?: (item: any) => boolean;
  
  /** Optional: custom className for styling */
  className?: string;
}
```

### Field Name Association

Each template includes a `fieldNames` array specifying which fields it applies to:

```typescript
EMAIL: (): LinkTemplate => ({
  id: 'email',
  icon: <FeatherMail />,
  tooltip: 'Email {{contact_email}}',
  urlTemplate: 'mailto:{{contact_email}}',
  fieldNames: ['contact_email', 'email'],  // Applies to items with these fields
  condition: (item) => !!item.contact_email || !!item.email,
})
```

When using automatic detection:
1. System scans item for fields
2. Matches fields against template `fieldNames` arrays
3. Generates buttons for matching templates
4. Conditions further filter which buttons appear

## Predefined Templates

### Communication Templates

**EMAIL** - Email links (mailto:)
- Fields: `contact_email`, `email`
- Icon: Mail
- Opens default email client

**PHONE** - Phone call links (tel:)
- Fields: `contact_phone`, `phone`
- Icon: Phone
- Opens phone app

**MS_TEAMS_CHAT** - Microsoft Teams chat deep link
- Fields: `contact_email`, `email`
- Icon: MessageSquare
- Condition: Only for actor types
- Opens Teams chat

**MS_TEAMS_CALL** - Microsoft Teams call deep link
- Fields: `contact_email`, `email`
- Icon: Phone
- Condition: Only for actor types
- Opens Teams call

**SLACK_DM** - Slack direct message deep link
- Fields: `slack_user_id`
- Icon: MessageSquare
- Opens Slack DM

### Lookup/Investigation Templates

**CMDB_LOOKUP** - Asset management system lookup
- Fields: `cmdb_id`
- Icon: Database
- Links to CMDB asset page

**USER_DIRECTORY** - User directory lookup
- Fields: `user_id`
- Icon: User
- Links to user profile

**THREAT_INTEL** - Threat intelligence lookup
- Fields: `observable_value`
- Icon: Search
- Links to threat intel search

## Template Interpolation

Templates support variable interpolation using `{{fieldName}}` syntax:

```typescript
// Simple field
urlTemplate: 'mailto:{{contact_email}}'
tooltip: 'Email {{contact_email}}'

// With URL encoding (automatic)
urlTemplate: 'https://example.com/search?q={{observable_value}}'
// Special characters in observable_value are automatically URL-encoded

// Nested field (dot notation)
urlTemplate: 'https://example.com/user/{{user.id}}'
tooltip: 'View {{user.name}}'
```

## Creating Custom Templates

### Simple Custom Template

```typescript
import { Link2 } from 'lucide-react';
import type { LinkTemplate } from '@/utils/linkTemplates';

const JIRA_TICKET: LinkTemplate = {
  id: 'jira-ticket',
  icon: <Link2 />,
  tooltip: 'View ticket {{ticket_id}}',
  urlTemplate: 'https://jira.company.com/browse/{{ticket_id}}',
  fieldNames: ['ticket_id', 'jira_id'],
  condition: (item) => !!item.ticket_id || !!item.jira_id,
};
```

### Adding to Global Templates

To make a template available for automatic detection, add it to the `ALL_TEMPLATES` array in `linkTemplates.tsx`:

```typescript
const ALL_TEMPLATES = [
  LINK_TEMPLATES.EMAIL(),
  LINK_TEMPLATES.PHONE(),
  // ... existing templates
  JIRA_TICKET,  // Add your custom template
];
```

### Template with Complex Conditions

```typescript
const INTERNAL_WIKI: LinkTemplate = {
  id: 'wiki-lookup',
  icon: <FeatherBook />,
  tooltip: 'Search wiki for {{name}}',
  urlTemplate: 'https://wiki.internal/search?q={{name}}',
  fieldNames: ['name', 'title'],
  condition: (item) => {
    // Only show for internal items with name/title
    return item.is_internal && (item.name || item.title);
  },
};
```

## API Reference

### Core Functions

**`generateAutoLinks(item: any)`**
- Automatically detects applicable templates and generates link configurations
- Returns: Array of link objects with url, tooltip, icon, id

**`detectLinkTemplates(item: any)`**
- Detects which templates apply to an item based on fields
- Returns: Array of applicable LinkTemplate objects

**`generateLinks(templates: LinkTemplate[], item: any)`**
- Generates link configurations from specific templates
- Returns: Array of link objects

**`interpolateTemplate(template: string, item: any)`**
- Interpolates {{variable}} placeholders with item data
- Returns: Interpolated string

**`interpolateUrl(template: string, item: any)`**
- Interpolates and URL-encodes template
- Returns: URL-safe interpolated string

### Utility Functions

**`generateAutoLinkButtons(item: any, options?)`**
- Generates LinkButton React components automatically
- Options: variant, size, className
- Returns: React node with buttons

**`generateLinkButtons(templates: LinkTemplate[], item: any, options?)`**
- Generates LinkButton components from specific templates
- Returns: React node with buttons

**`combineWithAutoLinks(customButtons: ReactNode, item: any)`**
- Combines custom buttons with auto-generated link buttons
- Returns: React node with all buttons

## Examples

### Actor with Contact Information

```tsx
const actor = {
  type: 'internal_actor',
  name: 'John Doe',
  contact_email: 'john@company.com',
  contact_phone: '+1-555-0123',
};

// Automatically generates:
// - Email button (mailto:john@company.com)
// - Phone button (tel:+1-555-0123)
// - Teams chat button (for internal actors only)
// - Teams call button (for internal actors only)

const cardProps = createTimelineCard(actor);
```

### Asset with CMDB Integration

```tsx
const asset = {
  type: 'asset',
  name: 'Laptop-1234',
  cmdb_id: 'ASSET-567890',
};

// Automatically generates:
// - CMDB lookup button

const links = generateAutoLinks(asset);
// [{ id: 'cmdb-lookup', url: 'https://cmdb.example.com/asset/ASSET-567890', ... }]
```

### Observable with Threat Intel

```tsx
const observable = {
  type: 'observable',
  observable_value: '192.168.1.1',
};

// Automatically generates:
// - Threat intel search button

const buttons = generateAutoLinkButtons(observable);
```

### Custom Template Usage

```tsx
import { generateLinkButtons } from '@/components/timeline/linkUtils';
import { LINK_TEMPLATES } from '@/utils/linkTemplates';

const customTemplates = [
  LINK_TEMPLATES.EMAIL('primary_email'),  // Use different field
  LINK_TEMPLATES.CMDB_LOOKUP(),
  {
    id: 'custom-tool',
    icon: <FeatherTool />,
    tooltip: 'Investigate {{hostname}}',
    urlTemplate: 'https://tools.company.com/host/{{hostname}}',
    fieldNames: ['hostname'],
    condition: (item) => !!item.hostname,
  },
];

const buttons = generateLinkButtons(customTemplates, item);
```

## Customization

### Modify Existing Templates

Templates can be customized by modifying `LINK_TEMPLATES` in `linkTemplates.tsx`:

```typescript
// Change CMDB URL
CMDB_LOOKUP: (cmdbIdField: string = 'cmdb_id'): LinkTemplate => ({
  id: 'cmdb-lookup',
  icon: <FeatherDatabase />,
  tooltip: `View in CMDB: {{${cmdbIdField}}}`,
  urlTemplate: `https://your-cmdb.company.com/asset/{{${cmdbIdField}}}`,  // Custom URL
  fieldNames: ['cmdb_id'],
  condition: (item) => !!item[cmdbIdField],
}),
```

### Configure MS Teams/Slack

Update the team ID for Slack integration:

```typescript
SLACK_DM: (userIdField: string = 'slack_user_id'): LinkTemplate => ({
  id: 'slack-dm',
  icon: <FeatherMessageSquare />,
  tooltip: `Message on Slack`,
  urlTemplate: `slack://user?team=T1234ABCD&id={{${userIdField}}}`,  // Your team ID
  fieldNames: ['slack_user_id'],
  condition: (item) => !!item[userIdField],
}),
```

### Add Organization-Specific Templates

Create templates for your organization's tools:

```typescript
// In linkTemplates.tsx
export const LINK_TEMPLATES = {
  // ... existing templates
  
  SERVICENOW: (incidentField: string = 'incident_id'): LinkTemplate => ({
    id: 'servicenow',
    icon: <FeatherAlertCircle />,
    tooltip: `View ServiceNow incident {{${incidentField}}}`,
    urlTemplate: `https://company.service-now.com/incident.do?sys_id={{${incidentField}}}`,
    fieldNames: ['incident_id', 'snow_id'],
    condition: (item) => !!item[incidentField],
  }),
};
```

Then add to `ALL_TEMPLATES` for automatic detection.

## Best Practices

1. **Use Automatic Detection**: Let the system detect appropriate links based on fields rather than manually configuring per type
2. **Consistent Field Naming**: Use consistent field names across item types (e.g., `contact_email` for all contact emails)
3. **Add fieldNames**: Always include `fieldNames` array in custom templates for automatic detection
4. **Meaningful Tooltips**: Include field values in tooltips so users know what they're clicking
5. **Test Conditions**: Use conditions to filter links appropriately (e.g., Teams links only for actors)
6. **URL Encoding**: Use `interpolateUrl()` for URL templates to ensure proper encoding
7. **Icon Consistency**: Use consistent icons for similar actions across different templates
