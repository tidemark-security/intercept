# GitHub Copilot Instructions

## Critical Workflow

**Before running ANY command:** `conda activate intercept`

**After changing backend models:**
```bash
./scripts/generate-types.sh  # Regenerates frontend/src/types/generated/
```
This generates TypeScript types + API clients from OpenAPI spec with automatic snake_case→camelCase conversion.

## Architecture Overview

Monorepo: FastAPI backend + React/TypeScript frontend + PostgreSQL

```
backend/app/
├── api/routes/       # FastAPI routers (thin layer)
├── services/         # Business logic (case_service.py, alert_service.py, etc.)
├── models/models.py  # ALL SQLModel models + Pydantic schemas (2000+ lines)
├── models/enums.py   # Shared enums
└── core/             # Config, database, security

frontend/src/
├── components/       # Type-based (buttons/, forms/) + Feature (timeline/, ai/)
├── hooks/            # React Query hooks (useAlerts, useCases, useTimelineForm)
├── types/generated/  # Auto-generated from backend OpenAPI spec
├── contexts/         # SessionProvider, ToastContext, TimelineFormContext
└── pages/            # Route-level components
```

## Backend Patterns

### Service Layer Pattern
Routes delegate to services; services contain all business logic:
```python
# routes/cases.py
@router.post("", response_model=CaseRead)
async def create_case(case_data: CaseCreate, db: AsyncSession = Depends(get_db)):
    return await case_service.create_case(db, case_data, current_user.username)

# services/case_service.py
async def create_case(self, db: AsyncSession, case_data: CaseCreate, created_by: str) -> Case:
    db_case = Case(**case_data.model_dump(), created_by=created_by)
    db.add(db_case)
    await db.flush()
    await self._create_audit_log(db, db_case.id, "created", ...)
    await db.commit()
    return db_case
```

### SQLModel Unified Pattern
All in `models/models.py` - Base → Table → Create/Update/Read schemas:
```python
class CaseBase(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    priority: Priority = Priority.MEDIUM

class Case(CaseBase, table=True):  # Database table
    id: Optional[int] = Field(default=None, primary_key=True)
    timeline_items: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))

class CaseCreate(CaseBase): pass
class CaseRead(CaseBase):
    id: int
    human_id: str  # Computed: "CAS-123"
```

### Timeline Items as JSONB
Alerts, Cases, Tasks store timeline as JSONB array with discriminated union types:
```python
class NoteItem(ItemBase):
    type: Literal["note"] = "note"

class TaskItem(ItemBase):
    type: Literal["task"] = "task"
    status: TaskStatus
    assignee: Optional[str]

# Union of all 17+ item types
CaseTimelineItem = Union[NoteItem, TaskItem, TTPItem, ObservableItem, ...]
```

### SQLModel Column Typing with `col()`
Use `col()` from SQLModel to get proper type inference for column expressions:
```python
from sqlmodel import col

# ✅ Use col() for static model column access
col(Case.status).in_([CaseStatus.NEW, CaseStatus.IN_PROGRESS])
col(Alert.updated_at).desc()
col(Task.title).ilike(search_pattern)

# ❌ Don't use col() with dynamic/variable model access
model = Alert  # or Case, Task - determined at runtime
model.status.in_(statuses)  # type: ignore[union-attr] - can't use col() here
```

**When to use `col()`:** Direct column access on a known model class (e.g., `Case.status`, `Alert.id`)

**When to use `# type: ignore`:**
- Dynamic model access via variable (`model.status` where `model` is a variable)
- `defer()` with JSONB columns (`defer(Case.timeline_items)`)
- `cast()` with nullable columns
- AsyncSession type mismatch between sqlalchemy/sqlmodel imports

### Database Migrations
```bash
cd backend
alembic revision --autogenerate -m "description"  # Generate
alembic upgrade head                               # Apply
```

## Frontend Patterns

### Generated Types Usage
Always import from generated types for API models:
```typescript
import type { CaseRead, AlertStatus } from '@/types/generated/models';
import { CasesService } from '@/types/generated/services/CasesService';
```

### Timeline Forms Architecture
Forms use context + hooks pattern (see `frontend/src/components/timeline/forms/AGENTS.md`):
```typescript
// Forms ONLY accept initialData prop - everything else from context
export function TaskForm({ initialData }: { initialData?: TaskItem }) {
  const { alertId, editMode, onCancel } = useTimelineFormContext();
  const { formState, setFormState, handleSubmit } = useTimelineForm({
    initialData,
    defaultState: { title: '', status: 'TODO' },
    buildPayload: (state) => ({ title: state.title, status: state.status }),
  });
}
```

### React Query Hooks Pattern
Custom hooks wrap React Query with consistent patterns:
```typescript
// hooks/useCases.ts - returns { data, isLoading, error }
export const useCases = (filters) => useQuery({
  queryKey: queryKeys.cases.list(filters),
  queryFn: () => CasesService.getCases(filters),
});
```

### Component Organization
- **Type folders** (`buttons/`, `forms/`, `overlays/`): Reusable UI primitives
- **Feature folders** (`timeline/`, `ai/`, `triage/`): Domain-specific, rarely reused

## Key Commands

```bash
# Development
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev

# Database
docker-compose up -d              # Start PostgreSQL
cd backend && alembic upgrade head

# Testing
cd backend && pytest
cd frontend && npm test

# Seed data
cd backend && python -m scripts.seed_test_users  # Creates admin/admin, analyst/analyst
```

## Testing

**Backend**: Unit test services, integration test routes. Use `tests/fixtures/` factories.
```python
# tests/integration/test_cases.py
async def test_create_case(async_client, auth_headers):
    response = await async_client.post("/api/v1/cases", json={"title": "Test"}, headers=auth_headers)
    assert response.status_code == 200
```

**Frontend**: Colocate tests as `Component.test.tsx`. Mock API with MSW.
```typescript
// components/timeline/NoteForm.test.tsx
it('submits note with title', async () => {
  render(<NoteForm />, { wrapper: TestProviders });
  await userEvent.type(screen.getByLabelText('Title'), 'My note');
  await userEvent.click(screen.getByRole('button', { name: /submit/i }));
});
```

**E2E**: Playwright specs in `frontend/e2e/`. Run: `cd frontend && npx playwright test`

## Extended Documentation

- **MCP Server** (AI tool integration): `docs/mcp/`
- **Search Architecture** (FTS, JSONB, fuzzy): `docs/search-architecture.md`
- **Background Tasks** (async job queue): `docs/task-queue.md`

## Common Gotchas

1. **Human IDs**: Entities have both `id` (int) and `human_id` (e.g., "CAS-123", "ALT-456"). API accepts both.
2. **Timeline mutations**: Use `useTimelineItemCreate` / `useUpdateTimelineItem` hooks, not direct service calls.
3. **Draft persistence**: Forms auto-save drafts in localStorage; disable with `persistDrafts: !editMode`.
4. **Auth**: Session-based with HTTP-only cookies, not JWT. Use `require_authenticated_user` dependency.
