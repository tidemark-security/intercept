# Components Directory

This directory contains all React components for the Intercept application, organized using a **hybrid approach**: type-based folders for generic UI primitives and feature folders for domain-specific modules.

## Folder Structure

```
components/
├── buttons/        # Button components (Button, IconButton, LinkButton, ToggleGroup)
├── forms/          # Form inputs (TextField, Select, DatetimePicker, TagInput, etc.)
├── feedback/       # User feedback (Toast, Alert, Loader, Progress, Skeleton*)
├── data-display/   # Data presentation (Table, Badge, Avatar, MarkdownContent, etc.)
├── overlays/       # Modals & popups (Dialog, Drawer, DropdownMenu, Tooltip)
├── cards/          # Card components (BaseCard, DashboardCard, StatCard, etc.)
├── navigation/     # Navigation (Tabs, Breadcrumbs, Paginator, Navbar, Sidebar)
├── misc/           # Miscellaneous (Accordion, IconWithBackground, Priority, State)
├── layout/         # Page layouts (DefaultPageLayout, ThreeColumnLayout, RightDock)
│
├── ai/             # AI chat feature (AiChat, ChatInput, messages, etc.)
├── auth/           # Authentication (SignIn, ChangePasswordForm, ProtectedRoute)
├── entities/       # Domain entities (CaseSelectorModal, EntityHeader, SystemType*)
├── search/         # Search feature (GlobalSearch, SearchResultRow, highlighting)
├── timeline/       # Timeline feature (UnifiedTimeline, cards, forms, handlers)
└── triage/         # Triage feature (TriageRecommendationCard, AIReasoning)
```

## When to Use Which Folder

### Type Folders (Generic Primitives)
Use these for **reusable UI components** that are used across multiple features:

| Folder | Use For |
|--------|---------|
| `buttons/` | Clickable actions (Button, IconButton, LinkButton) |
| `forms/` | User inputs (text, select, date, etc.) |
| `feedback/` | Status indicators (loading, toasts, alerts, skeletons) |
| `data-display/` | Presenting data (tables, badges, avatars, markdown) |
| `overlays/` | Floating UI (modals, drawers, tooltips, dropdowns) |
| `cards/` | Card-based layouts and containers |
| `navigation/` | Navigation patterns (tabs, breadcrumbs, sidebars) |
| `misc/` | Components that don't fit elsewhere |
| `layout/` | Page-level layout structures |

### Feature Folders (Domain-Specific)
Use these for **components specific to a feature** that are unlikely to be reused elsewhere:

| Folder | Purpose |
|--------|---------|
| `ai/` | AI chat interface and related components |
| `auth/` | Authentication flows and protected routes |
| `entities/` | Case/Alert/Task entity-specific UI |
| `search/` | Global search functionality |
| `timeline/` | Timeline display, forms, and event handlers |
| `triage/` | AI triage recommendations and feedback |

## Decision Heuristic

When adding a new component, ask yourself:

1. **Is this component specific to one feature?**
   - Yes → Put it in the feature folder (e.g., `timeline/`, `ai/`)
   - No → Continue to step 2

2. **What is the component's primary purpose?**
   - User input → `forms/`
   - Button/action → `buttons/`
   - Feedback/status → `feedback/`
   - Display data → `data-display/`
   - Modal/popup → `overlays/`
   - Card container → `cards/`
   - Navigation → `navigation/`
   - Page layout → `layout/`
   - None of the above → `misc/`

## Import Conventions

Each folder has an `index.ts` barrel file for cleaner imports:

```typescript
// Preferred: Import from folder barrel
import { Button, IconButton } from '@/components/buttons';
import { TextField, Select } from '@/components/forms';

// Also valid: Direct file import
import { Button } from '@/components/buttons/Button';
```

## Adding New Components

1. **Determine the appropriate folder** using the heuristic above
2. **Create the component file** (e.g., `MyComponent.tsx`)
3. **Export from the barrel file** by adding to the folder's `index.ts`:
   ```typescript
   export { MyComponent } from './MyComponent';
   ```
4. **For feature folders**, follow any folder-specific documentation (e.g., `timeline/README.md`)

## Timeline-Specific Documentation

The `timeline/` folder has its own detailed documentation:
- [timeline/README.md](timeline/README.md) - Architecture and usage
- [timeline/forms/AGENTS.md](timeline/forms/AGENTS.md) - Form component patterns
