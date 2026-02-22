# Timeline Form Components

Forms use **context-based architecture** with centralized logic.

## Architecture

- **Props:** Forms only accept `initialData?: ItemType`
- **Hook:** `useTimelineForm` handles state, drafts, mutations, validation
- **Layout:** `TimelineFormLayout` provides consistent UI

## Quick Start

```typescript
import { useTimelineForm } from '@/hooks/useTimelineForm';
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';

interface MyFormProps {
  initialData?: ItemType;
}

export function MyForm({ initialData }: MyFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  
  const { formState, setFormState, handleSubmit, handleClear, isSubmitting } = useTimelineForm({
    initialData,
    defaultState: { title: '', description: '' },
    transformInitialData: (data) => ({
      title: data.title || '',
      description: data.description || '',
    }),
    buildPayload: (state) => ({
      title: state.title,
      description: state.description || undefined,
    }),
    validate: (state) => {
      if (!state.title.trim()) return { valid: false, error: "Title required" };
      return { valid: true };
    },
  });

  return (
    <TimelineFormLayout
      title={editMode ? "Edit Item" : "Add Item"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitDisabled={!formState.title.trim()}
      isSubmitting={isSubmitting}
    >
      <TextField label="Title">
        <TextField.Input 
          value={formState.title}
          onChange={(e) => setFormState(prev => ({ ...prev, title: e.target.value }))}
        />
      </TextField>
    </TimelineFormLayout>
  );
}
```

## Context Values

`useTimelineFormContext()` provides:
- `alertId` - Alert ID
- `itemType` - Timeline item type (e.g., 'note', 'task')
- `editMode` - Create (false) or edit (true)
- `parentItemId` - Parent ID for replies (null for top-level)
- `onSuccess` - Success callback
- `onCancel` - Cancel callback

## useTimelineForm Hook

**Handles automatically:**
- Draft persistence (disabled in edit mode)
- Create/update mutations
- Parent ID injection for replies
- Toast notifications
- Draft cleanup
- Form reset
- Loading states

**Config:**
- `initialData` - Pre-populate in edit mode
- `defaultState` - Default for new items
- `transformInitialData` - Convert initialData to form state
- `buildPayload` - Build mutation payload
- `validate` - Validation function

**Returns:**
- `formState`, `setFormState` - State
- `handleSubmit` - Submit handler
- `handleClear` - Reset & delete draft
- `isSubmitting` - Loading state
- `resetCounter` - For MarkdownInput keys
- Context values (for convenience)

## Manual Hook Usage (Advanced)

```typescript
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';
import { useFormWithDraft } from '@/hooks/useFormWithDraft';
import { useTimelineItemCreate } from '@/hooks/useTimelineItemCreate';
import { useUpdateTimelineItem } from '@/hooks/useUpdateTimelineItem';

export function MyForm({ initialData }: MyFormProps) {
  const { alertId, itemType, editMode, parentItemId, onSuccess, onCancel } = useTimelineFormContext();
  
  const [formState, setFormState, { clearDraft, handleClear }] = useFormWithDraft(
    alertId, itemType,
    initialData ? { title: initialData.title || '' } : { title: '' },
    { persistDrafts: !editMode }
  );
  
  const createMutation = useTimelineItemCreate(alertId, {
    parentItemId: parentItemId || undefined,
    onSuccess: (data, itemId) => { clearDraft(); handleClear(); onSuccess?.(itemId); },
  });

  const updateMutation = useUpdateTimelineItem(alertId, {
    onSuccess: () => onSuccess?.(initialData?.id),
  });

  const handleSubmit = () => {
    if (!formState.title.trim()) return;
    if (editMode && initialData?.id) {
      updateMutation.mutate({ itemId: initialData.id, updates: { type: itemType, title: formState.title } });
    } else {
      createMutation.mutate({ id: uuidv4(), type: itemType, title: formState.title });
    }
  };
}
```

## Common Patterns

### Auto-Focus (Create Mode Only)
```typescript
const inputRef = React.useRef<HTMLInputElement>(null);
React.useEffect(() => {
  if (!editMode) {
    const timer = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(timer);
  }
}, [editMode]);
```

### MarkdownInput with Reset
```typescript
<MarkdownInput
  key={`markdown-${alertId}-${resetCounter}`}
  value={formState.description}
  onChange={(value) => setFormState(prev => ({ ...prev, description: value || "" }))}
/>
```

### Shared Components
- `TagsManager` - Tag input/display
- `DateTimeManager` - Timestamp with "Now" button
- `MarkdownInput` - Rich text editor

### Validation
```typescript
// Disable submit
submitDisabled={!formState.title.trim()}

// In handler
if (!formState.url.trim()) {
  showToast("Error", "URL required", "error");
  return;
}
```

## Best Practices

**DO:**
- ✅ Use `useTimelineForm` (simplest)
- ✅ Get props from `useTimelineFormContext()`
- ✅ Only accept `initialData` as prop
- ✅ Use `persistDrafts: !editMode` (manual mode)
- ✅ Import types from `@/types/generated/models`
- ✅ Only include optional fields if they have values

**DON'T:**
- ❌ Don't accept `alertId`, `onSuccess`, `editMode` as props
- ❌ Don't manually inject `parent_id`
- ❌ Don't persist drafts in edit mode
- ❌ Don't show Clear in edit mode
- ❌ Don't include empty optional fields

---

**Reference:** `NoteForm.tsx`, `TaskForm.tsx`, `ActorForm.tsx`
