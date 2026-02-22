# TypeScript Type Generation

This directory contains scripts to automatically generate TypeScript types from the FastAPI backend's OpenAPI specification.

## Overview

The type generation process:
1. Activates the appropriate conda environment (`intercept`)
2. Imports the FastAPI app from the backend
3. Extracts the OpenAPI specification using `app.openapi()`
4. Uses `openapi-typescript-codegen` to generate TypeScript types and API client
5. Applies camelCase transformation to field names for TypeScript conventions
6. Creates field mapping utilities for automatic snake_case ↔ camelCase conversion
7. Outputs generated types to `frontend/src/types/generated/`

## Files

- `generate-types.py` - Main Python script that handles the generation process
- `generate-types.sh` - Shell script wrapper for easier execution
- `README.md` - This documentation

## Prerequisites

- Python 3.9+ with FastAPI backend dependencies installed
- Node.js and npm with frontend dependencies installed
- Conda environments: `intercept`
- Backend FastAPI app should be importable from the backend directory

## Usage

### Quick Start

From the project root directory:

```bash
./scripts/generate-types.sh
```

### Manual Execution

```bash
# From project root
python3 scripts/generate-types.py
```

### NPM Script

```bash
# From frontend directory
npm run generate-types
```

## Generated Output

The script generates the following in `frontend/src/types/generated/`:

- `models/` - TypeScript interfaces for all API models (with camelCase field names)
- `services/` - API client methods for all endpoints
- `core/` - Core API configuration and types
- `fieldMapper.ts` - Utilities for converting between camelCase and snake_case
- `index.ts` - Main export file with all types and utilities

## Integration with Existing Types

The script automatically:
1. Adds an export for generated types to `frontend/src/types/index.ts`
2. Generates camelCase field names for TypeScript conventions while maintaining backend snake_case
3. Creates field mapping utilities (`fieldMapper.ts`) for automatic API data conversion
4. Provides seamless integration between frontend camelCase and backend snake_case naming
5. Enables gradual migration from manual to generated types

## Field Mapping and Naming Conventions

The generated types automatically handle the naming convention differences between Python (snake_case) and TypeScript (camelCase):

### Backend (Python/FastAPI)
```python
class CaseRead(BaseModel):
    case_number: str
    created_at: datetime
    assigned_to: Optional[str]
```

### Generated Frontend Types
```typescript
interface CaseRead {
    caseNumber: string;
    createdAt: string;
    assignedTo?: string;
}
```

### Automatic Field Mapping

The generated `fieldMapper.ts` provides utilities for seamless conversion:

```typescript
import { fieldMapper, toCamelCase, toSnakeCase } from '../types/generated/fieldMapper';

// Convert API response to frontend format
const frontendData = fieldMapper.toCamelCase(apiResponse);

// Convert frontend data to API format
const apiData = fieldMapper.toSnakeCase(frontendFormData);
```

This ensures that:
- Frontend code uses TypeScript conventions (camelCase)
- Backend API uses Python conventions (snake_case)  
- Data conversion is automatic and type-safe
- No manual field mapping is required

## Timeline Data Handling

The generation script properly handles the timeline system where the backend stores timeline items as flexible JSON (`Dict[str, Any]`) while the frontend needs structured types:

### Backend Storage
```python
# Timeline items stored as flexible JSONB
timeline_items: Optional[Dict[str, Any]] = Field(default_factory=dict)
```

### Frontend Types
```typescript
// Generated timeline utilities in utils/timelineUtils.ts
interface TimelineItem {
    id: string;
    type: TimelineItemType;
    content: string;
    createdAt: string;
    // ... other fields
}

// Flexible mock data interface matching backend
interface MockTimelineItem {
    id: string;
    type: string;
    content: string;
    // ... flexible fields matching backend's Dict[str, Any]
}
```

The timeline utilities handle conversion between the flexible backend format and the structured frontend types automatically.

## Best Practices

1. **Run after backend changes**: Execute the script whenever you modify API models or endpoints
2. **Version control**: Commit generated types to track API changes
3. **Migration strategy**: Gradually replace manual types with generated ones
4. **Validation**: Always test the frontend after regenerating types

## Configuration

The script can be customized by modifying `generate-types.py`:

- Output directory: Change `output_dir` variable
- Conda environments: Modify `backend_env` and `frontend_env` variables
- Generation options: Modify the `openapi-typescript-codegen` command arguments
- Client type: Currently set to `axios` client
- Field transformation: Customize the camelCase conversion logic

## Troubleshooting

### Common Issues

1. **Backend import fails**: Ensure backend dependencies are installed and the `intercept` conda environment exists
2. **Frontend build fails**: Ensure the `intercept-cases-frontend` conda environment exists with required dependencies
3. **Missing dependencies**: The script will automatically install `openapi-typescript-codegen` if missing
4. **Permission errors**: Make sure the script has executable permissions (`chmod +x generate-types.sh`)
5. **Conda environment not found**: Create the required environments using the `.yml` files in backend/frontend directories


## Development Workflow

### After Backend Changes

1. Make changes to FastAPI models/endpoints in the backend
2. Run `./scripts/generate-types.sh` from the project root
3. The script will automatically:
   - Activate required conda environments
   - Generate new TypeScript types with camelCase conversion
   - Update field mapping utilities
   - Preserve existing timeline and custom utilities
4. Update frontend code to use new/updated types (if any new fields added)
5. Test the application with both mock data and API integration
6. Commit both backend changes and generated frontend types

### Type Safety Verification

```bash
# Verify types compile correctly
cd frontend && npm run build

# Run type checking only
cd frontend && npx tsc --noEmit
```

### Migration from Manual Types

1. **Gradual Migration**: Replace manual type imports with generated ones
2. **Field Mapping**: Use `fieldMapper` utilities for API data conversion  
3. **Timeline Data**: Use timeline utilities for flexible timeline handling
4. **Validation**: Ensure all components compile after type changes

This workflow ensures your frontend and backend stay perfectly synchronized with minimal manual effort and maximum type safety.
