# Timeline Card Factory

A factory pattern for generating BaseCard components from timeline items. Supports all 17+ timeline item types with type-specific field mappings, icons, and colors.

## Features

- ✅ Supports all 17+ timeline item types
- ✅ Handler-owned, type-specific title generation
- ✅ Type-specific field→card mapping rules  
- ✅ Centralized icon map for consistency
- ✅ Item-specific color coding (not based on alert priority)
- ✅ Generic fallback for future types
- ✅ Timestamp formatting utilities
- ✅ Graceful handling of missing/null fields
- ✅ Structured logging for observability
- ✅ Factory pattern with handler registry

## Important Note About Titles

Handlers generate titles for their own item types (for example, task uses `task_human_id`, system uses `hostname`, TTP uses `mitre_id` + technique title). The factory only applies a generic fallback title via `getTypeTitle()` when a handler returns no title.

## Usage

### Basic Usage

```tsx
import { createTimelineCard } from '@/components/timeline/TimelineCardFactory';
import { BaseCard } from '@/components/BaseCard';
import type { TimelineItem } from '@/types/timeline';

// Import handlers to register them
import '@/components/timeline/eventHandlers';

function TimelineItemCard({ item }: { item: TimelineItem }) {
  const cardProps = createTimelineCard(item);
  return <BaseCard {...cardProps} />;
}
```

### With Options

```tsx
import { IconButton } from '@/components/IconButton';
import { Link2, Terminal, Share2 } from 'lucide-react';

const cardProps = createTimelineCard(item, {
  size: 'medium',  // 'small' | 'medium' | 'large'
  onClick: (item) => console.log('Card clicked:', item),
  actionButtons: (
    <div className="flex gap-1">
      <IconButton icon={<FeatherLink2 />} variant="neutral-tertiary" size="small" />
      <IconButton icon={<FeatherTerminal />} variant="neutral-tertiary" size="small" />
      <IconButton icon={<FeatherShare2 />} variant="neutral-tertiary" size="small" />
    </div>
  ),
});
```

### Rendering Multiple Items

```tsx
function TimelineList({ items }: { items: TimelineItem[] }) {
  return (
    <div className="flex flex-col gap-4">
      {items.map((item) => {
        const cardProps = createTimelineCard(item);
        return <BaseCard key={item.id} {...cardProps} />;
      })}
    </div>
  );
}
```

## Supported Timeline Item Types

The factory automatically dispatches to the appropriate handler for each type:

1. **Note** - Simple text notes
2. **Task** - Action items with status, assignee, due date
3. **Observable** - IOCs (IP addresses, domains, hashes, etc.)
4. **TTP** - MITRE ATT&CK tactics, techniques, procedures
5. **System** - Host/system information with risk indicators
6. **InternalActor** - Internal users with VIP/privileged flags
7. **ExternalActor** - External contacts (customers, vendors, partners)
8. **ThreatActor** - Malicious actors with threat intelligence
9. **Attachment** - File attachments with metadata
10. **Email** - Email communications
11. **Link** - URLs and external references
12. **ForensicArtifact** - Evidence artifacts with hashes
13. **Alert** - Security alerts with priority
14. **Case** - Related case references
15. **NetworkTraffic** - Network connection details
16. **Process** - Process execution information
17. **RegistryChange** - Windows registry modifications

## Field Mapping Examples

**Note**: Handlers should provide `title` along with line fields and other properties. The factory provides a generic fallback only when handler title is missing.

### Task Item

- **Title**: Task human ID (or generic fallback)
- **Line1**: Status (NEW, IN PROGRESS, COMPLETED, etc.)
- **Line2**: Assignee (if present)
- **Line3**: Due date (if present)
- **Color**: Based on status and overdue state
  - Completed: success (green)
  - Overdue: error (red)
  - In Progress: warning (yellow)

### System Item

- **Title**: Hostname
- **Line1**: IP address
- **Line2**: System type
- **Line3**: Characteristics (Critical, High Risk, Internet Facing, etc.)
- **Color**: Based on risk indicators
  - Critical systems: error (red)
  - High risk systems: warning (yellow)

### Observable Item

- **Title**: Observable value (or generic fallback)
- **Line1**: Observable value
- **Line2**: Description (if present)
- **Color**: default (neutral)

## Icon Map

Icons are centralized in `@/utils/timelineIcons.ts` and extracted from existing AddItemForm components:

```tsx
import { getTimelineIcon } from '@/utils/timelineIcons';

const Icon = getTimelineIcon('note');  // Returns FeatherNotebookText
const Icon = getTimelineIcon('task');  // Returns FeatherCheckSquare
// ... etc
```

## Adding New Timeline Item Types

To add support for a new timeline item type:

1. Create a handler in `eventHandlers/`:

```tsx
// myNewHandler.tsx
export function isMyNewItem(item: TimelineItem): item is MyNewItem {
  return item.type === 'my_new_type';
}

export function handleMyNewItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  const Icon = getTimelineIcon('my_new_type');
  
  return {
    title: item.someField,
    line1: item.anotherField,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
```

2. Register it in `eventHandlers/index.ts`:

```tsx
import { handleMyNewItem } from './myNewHandler';
registerHandler('my_new_type', handleMyNewItem);
```

3. Add the icon to `timelineIcons.ts`:

```tsx
export const TIMELINE_ICONS: Record<TimelineItemType, ...> = {
  // ...
  my_new_type: FeatherSomeIcon,
};
```

## Color System

Cards use the `system` prop to indicate severity/status:

- `default`: Neutral, informational items
- `success`: Positive outcomes (e.g., completed tasks)
- `warning`: Caution items (e.g., in-progress tasks, high-risk systems)
- `error`: Critical items (e.g., threat actors, critical systems)

Colors are **item-specific** and based on the item's characteristics, not inherited from alert/case priority.

## Logging and Observability

The factory emits structured logs for:

- Unknown timeline item types (warns and uses fallback handler)
- Development warnings with full item data
- Production JSON logs for monitoring

```tsx
// Development
console.warn('No handler registered for timeline item type: xyz', item);

// Production
console.log(JSON.stringify({
  level: 'warn',
  message: 'Unknown timeline item type',
  type: 'xyz',
  itemId: '123',
  timestamp: '2024-11-08T10:30:00Z'
}));
```

## API Reference

### `createTimelineCard(item, options?)`

Main factory function that generates BaseCard props from a timeline item.

**Parameters:**
- `item: TimelineItem` - The timeline item to render
- `options?: CardFactoryOptions` - Optional configuration

**Returns:** `CardConfig` - Props to spread onto BaseCard component

### `CardFactoryOptions`

```tsx
interface CardFactoryOptions {
  size?: 'large' | 'medium' | 'small';
  onClick?: (item: TimelineItem) => void;
  actionButtons?: React.ReactNode;
}
```

### `CardConfig`

```tsx
interface CardConfig {
  title?: React.ReactNode;
  baseIcon?: React.ReactNode;
  line1?: React.ReactNode;
  line2?: React.ReactNode;
  line3?: React.ReactNode;
  line4?: React.ReactNode;
  system?: 'default' | 'success' | 'warning' | 'error';
  size?: 'large' | 'medium' | 'small';
  actionButtons?: React.ReactNode;
  _item?: TimelineItem;  // Original item for reference
}
```

### Utility Functions

```tsx
// Check if a handler is registered
hasHandler('note');  // true

// Get all registered types
getRegisteredTypes();  // ['alert', 'attachment', 'case', ...]

// Get icon for a type
getTimelineIcon('note');  // FeatherNotebookText

// Format timestamps
formatTimelineTimestamp('2024-11-08T10:30:00Z');  // "2 hours ago" or "Nov 8, 2024 10:30 AM"
```

## Architecture

```
timeline/
├── TimelineCardFactory.tsx    # Main factory with handler registry
├── eventHandlers/
│   ├── index.ts              # Handler exports and registration
│   ├── noteHandler.tsx       # Note item handler
│   ├── taskHandler.tsx       # Task item handler
│   ├── observableHandler.tsx # Observable item handler
│   ├── ttpHandler.tsx        # TTP item handler
│   ├── systemHandler.tsx     # System item handler
│   ├── actorHandlers.tsx     # Actor item handlers (3 types)
│   ├── attachmentHandler.tsx # Attachment item handler
│   ├── emailHandler.tsx      # Email item handler
│   ├── linkHandler.tsx       # Link item handler
│   ├── forensicArtifactHandler.tsx # Forensic artifact item handler
│   ├── alertHandler.tsx      # Alert item handler
│   ├── caseHandler.tsx       # Case item handler
│   ├── networkTrafficHandler.tsx # Network traffic item handler
│   ├── processHandler.tsx    # Process item handler
│   └── registryChangeHandler.tsx # Registry change item handler
└── README.md                 # This file

utils/
├── timelineIcons.ts          # Centralized icon map
└── dateFormatters.ts         # Timestamp formatting utilities
```

## Testing

```bash
# Run date formatter tests
npm test -- dateFormatters.test.ts

# Run all tests
npm test
```
