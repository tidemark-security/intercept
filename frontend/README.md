# Intercept Frontend

React-based frontend for the Intercept security case management platform.

## Tech Stack

- **React**: 18
- **TypeScript**: 5.x
- **Build Tool**: Vite
- **Routing**: React Router DOM v6.30+
- **Styling**: Tailwind CSS v3
- **Icons**: Feather React
- **HTTP Client**: Native Fetch API
- **Testing**: Vitest + React Testing Library

## Prerequisites

1. **Conda Environment**: Activate the project environment
   ```bash
   conda activate intercept
   ```

2. **Backend API**: Running instance at `http://localhost:8000`
   ```bash
   cd ../backend
   uvicorn app.main:app --reload
   ```

3. **Node.js**: Installed via conda environment

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Generate TypeScript Types

After any backend API changes, regenerate types:

```bash
cd ..
./scripts/generate-types.sh
```

This generates TypeScript types from OpenAPI schema in `src/types/generated/`.

### 3. Environment Configuration

The frontend connects to the backend API. If running on non-standard ports, update the API URL in your development setup.

## UX Component Library

Many UI components are imported from `@tidemark-security/ux`, a shared component library. In production, the package is installed from the Git repository. For local development, you can link a local clone so changes are reflected immediately.

### Setting up local UX development

1. **Clone the UX repo** as a sibling directory:

   ```bash
   cd ~/projects          # or wherever tmi/ lives
   git clone https://github.com/tidemark-security/ux.git
   ```

   Your directory structure should look like:
   ```
   ~/projects/
   ├── tmi/
   │   └── frontend/      # this project
   └── ux/                # UX component library
   ```

2. **Build the UX library** (required — TMI consumes the dist bundle):

   ```bash
   cd ~/projects/ux
   npm install
   npm run build
   ```

3. **Link UX into the frontend** using `npm link`:

   ```bash
   # Step 1: Register UX as a globally linkable package
   cd ~/projects/ux
   npm link

   # Step 2: Create the symlink in TMI's node_modules
   cd ~/projects/tmi/frontend
   npm link @tidemark-security/ux
   ```

   This creates `node_modules/@tidemark-security/ux → ~/projects/ux`. Any rebuild of the UX dist is immediately available without reinstalling.

4. **After making UX changes**, rebuild the dist:

   ```bash
   cd ~/projects/ux
   npm run build
   ```

   The frontend dev server (Vite) will hot-reload automatically.

### Unlinking

To go back to the Git-based version:

```bash
cd ~/projects/tmi/frontend
npm unlink @tidemark-security/ux
npm install
```

> **Note:** Running `npm install` in the frontend will also remove the link and restore the Git-based version.

### How `npm link` works

`npm link` is a two-step process:

1. **`npm link`** (in the package directory) — creates a global symlink from Node's global `node_modules` to that directory.
2. **`npm link <package-name>`** (in the consumer) — creates a symlink in the consumer's `node_modules` pointing to the global symlink.

The linked package resolves its own dependencies from *its own* `node_modules`, not the consumer's. This is why `vite.config.ts` includes resolve aliases for `react`, `react-dom`, and `react-router-dom` — they force a single copy of React across both packages.

## Running the Application

### Development Mode

```bash
npm run dev
```

The application will be available at http://localhost:5173 (Vite default).

### Production Build

```bash
# Build for production
npm run build

# Preview production build locally
npm run preview
```

## Authentication Flow

### Login

1. User enters username and password on `/login` page
2. Frontend calls `POST /api/v1/auth/login`
3. Backend sets HTTP-only session cookie
4. User redirected to home page
5. Session context populated with user details

### Protected Routes

All routes except `/login` are protected by `<ProtectedRoute>` component:

```typescript
<Route path="/alerts" element={
  <ProtectedRoute>
    <Alerts />
  </ProtectedRoute>
} />
```

If user is not authenticated, they're redirected to `/login`.

### Password Change Flows

#### Forced Password Change (After Admin Reset)

1. User logs in with temporary password
2. `mustChangePassword` flag detected in session
3. `Login` component displays `<ChangePasswordForm forced={true} />`
4. User must change password before accessing application
5. Warning banner displayed: "You must change your password to continue"
6. Logout button available (cancel button hidden)

#### Voluntary Password Change

1. User navigates to `/settings/password`
2. `SelfPasswordChange` page displays `<ChangePasswordForm forced={false} />`
3. User enters current password and new password
4. No warning banner displayed
5. Cancel button available (logout button hidden)

### Session Management

The `SessionContext` provides global authentication state:

```typescript
const {
  user,              // Current user details
  status,            // 'authenticated' | 'unauthenticated' | 'authenticating'
  mustChangePassword, // Force password change flag
  login,             // Login function
  logout,            // Logout function
  isAdmin,           // Role check helpers
  isAnalyst,
  isAuditor
} = useSession();
```

### Logout

1. User clicks logout button
2. Frontend calls `POST /api/v1/auth/logout`
3. Backend invalidates session
4. Frontend clears session context
5. User redirected to `/login`

## Project Structure

```
frontend/
├── src/
│   ├── main.tsx                # Application entry point
│   ├── App.tsx                 # Root component with routing
│   ├── index.css               # Global styles (Tailwind)
│   ├── components/
│   │   ├── ChangePasswordForm.tsx   # Reusable password change form
│   │   └── ProtectedRoute.tsx       # Authentication guard
│   ├── contexts/
│   │   └── sessionContext.tsx       # Global session state
│   ├── pages/
│   │   ├── Login.tsx                # Login page
│   │   ├── SelfPasswordChange.tsx   # Voluntary password change
│   │   ├── AdminUsers.tsx           # Admin user management
│   │   └── ...                      # Other pages
│   ├── types/
│   │   └── generated/               # Auto-generated from OpenAPI
│   │       ├── services/
│   │       │   ├── AuthenticationService.ts
│   │       │   └── ...
│   │       └── core/
│   └── ui/                          # Externally-managed UI components
│       ├── components/              # DO NOT MODIFY
│       └── layouts/                 # DO NOT MODIFY
└── tests/
    └── auth/                        # Authentication tests
        ├── login.test.tsx
        ├── password-change.test.tsx
        └── admin-users.test.tsx
```

**Important**: Components under `src/ui/` are externally managed and must not be modified directly unless explicitly instructed.

## Testing

### Run All Tests

```bash
npm run test
```

### Run Specific Test File

```bash
npm run test -- login.test.tsx
```

### Run Tests in Watch Mode

```bash
npm run test -- --watch
```

### Coverage Report

```bash
npm run test -- --coverage
```

## Common Tasks

### Add a New Page

1. Create page component in `src/pages/`
2. Add route in `App.tsx`
3. Wrap with `<ProtectedRoute>` if authentication required
4. Add navigation link (if applicable)

Example:
```typescript
// src/pages/NewPage.tsx
export default function NewPage() {
  const { user } = useSession();
  
  return (
    <div>
      <h1>New Page</h1>
      <p>Welcome, {user?.username}!</p>
    </div>
  );
}

// App.tsx
<Route path="/new-page" element={
  <ProtectedRoute>
    <NewPage />
  </ProtectedRoute>
} />
```

### Call a Backend API

Use generated TypeScript services:

```typescript
import { AuthenticationService } from '@/types/generated/services/AuthenticationService';
import { ApiError } from '@/types/generated/core/ApiError';

try {
  await AuthenticationService.changePasswordApiV1AuthPasswordChangePost({
    requestBody: {
      currentPassword: "old",
      newPassword: "new"
    }
  });
  console.log("Success!");
} catch (err) {
  if (err instanceof ApiError) {
    console.error(`API Error: ${err.status} - ${err.message}`);
  }
}
```

### Add Role-Based Access Control

Use role helpers from session context:

```typescript
const { isAdmin, isAnalyst } = useSession();

return (
  <div>
    {isAdmin && <AdminPanel />}
    {isAnalyst && <AnalystDashboard />}
  </div>
);
```

Or protect entire routes:

```typescript
{user?.role === "ADMIN" && (
  <Route path="/admin/users" element={
    <ProtectedRoute>
      <AdminUsers />
    </ProtectedRoute>
  } />
)}
```

### Handle Form Validation

Use controlled components with state:

```typescript
const [username, setUsername] = useState("");
const [error, setError] = useState<string | null>(null);

const handleSubmit = async () => {
  if (!username.trim()) {
    setError("Username is required");
    return;
  }
  
  try {
    await someApiCall(username);
  } catch (err) {
    setError("API call failed");
  }
};

return (
  <TextField error={!!error} helpText={error || ""}>
    <TextField.Input 
      value={username}
      onChange={(e) => setUsername(e.target.value)}
    />
  </TextField>
);
```

## Troubleshooting

### TypeScript Errors After Backend Changes

**Symptom**: TypeScript errors about missing or mismatched types

**Solution**: Regenerate types from backend OpenAPI schema
```bash
cd ..
./scripts/generate-types.sh
```

### Session Cookie Not Set

**Symptom**: Login appears successful but user immediately logged out

**Solution**: 
- Check that backend is setting `Set-Cookie` header
- Verify `credentials: 'include'` in fetch calls
- Check browser console for CORS errors
- Ensure `withCredentials: true` in API client config

### Protected Routes Not Working

**Symptom**: Can access protected pages without logging in

**Solution**: Verify route is wrapped with `<ProtectedRoute>`
```typescript
// ✅ Correct
<Route path="/secure" element={
  <ProtectedRoute>
    <SecurePage />
  </ProtectedRoute>
} />

// ❌ Wrong
<Route path="/secure" element={<SecurePage />} />
```

### Password Change Form Not Appearing

**Symptom**: After admin password reset, user not prompted to change password

**Solution**:
- Check `mustChangePassword` in session response
- Verify `Login.tsx` conditionally renders `<ChangePasswordForm>`
- Check `sessionContext.tsx` properly sets `mustChangePassword` state

### Build Errors in Production

**Symptom**: `npm run build` fails with type errors

**Solution**:
```bash
# Clean node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Regenerate types
cd .. && ./scripts/generate-types.sh

# Retry build
cd frontend && npm run build
```

### Tests Failing Unexpectedly

**Symptom**: Tests pass locally but fail in CI

**Solution**:
- Check for timing issues (use `waitFor` for async operations)
- Ensure mocks are properly setup in `beforeEach`
- Clear mocks between tests with `vi.clearAllMocks()`
- Check for hardcoded values (dates, UUIDs) that should be mocked

## Component Library (UI)

The project uses an externally-managed component library under `src/ui/`. These components are:

- **Externally synchronized**: Changes made here will be overwritten
- **Do not modify**: Create wrapper components instead
- **Reference only**: Use as-is or compose into custom components

### Available Components

- **Button**: Primary, secondary, tertiary variants
- **TextField**: Text input with label, help text, error states
- **SignIn**: Complete sign-in form template
- **OAuthSocialButton**: Social login buttons
- **LinkAlertDialog**: Modal dialog component

### Using UI Components

```typescript
import { Button } from '@/ui/components/Button';
import { TextField } from '@/ui/components/TextField';

function MyForm() {
  return (
    <div>
      <TextField label="Username">
        <TextField.Input placeholder="Enter username" />
      </TextField>
      
      <Button variant="primary" onClick={handleSubmit}>
        Submit
      </Button>
    </div>
  );
}
```

## Security Best Practices

### Password Validation

Always validate passwords on both frontend and backend:

```typescript
const validatePassword = (password: string): string | null => {
  if (password.length < 12) {
    return "Password must be at least 12 characters";
  }
  if (!/[A-Z]/.test(password)) {
    return "Password must include uppercase letter";
  }
  if (!/[a-z]/.test(password)) {
    return "Password must include lowercase letter";
  }
  if (!/[0-9]/.test(password)) {
    return "Password must include number";
  }
  if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
    return "Password must include special character";
  }
  return null;
};
```

### Sensitive Data Handling

- Never log passwords or session tokens
- Use POST for sensitive data (not GET with query params)
- Clear sensitive form data after submission
- Display generic error messages (don't reveal if username exists)

### XSS Prevention

- React escapes content by default
- Avoid `dangerouslySetInnerHTML`
- Sanitize user-generated content before display
- Use Content Security Policy headers

## Performance Optimization

### Code Splitting

Large pages automatically code-split with React Router:

```typescript
import { lazy, Suspense } from 'react';

const AdminUsers = lazy(() => import('./pages/AdminUsers'));

<Route path="/admin/users" element={
  <Suspense fallback={<LoadingSpinner />}>
    <ProtectedRoute>
      <AdminUsers />
    </ProtectedRoute>
  </Suspense>
} />
```

### Memoization

Use `useMemo` and `useCallback` for expensive computations:

```typescript
const filteredUsers = useMemo(() => 
  users.filter(u => u.role === selectedRole),
  [users, selectedRole]
);

const handleClick = useCallback(() => {
  doSomething(prop);
}, [prop]);
```

## Deployment

### Build for Production

```bash
npm run build
```

Output in `dist/` directory.

### Environment Variables

Create `.env.production` for production-specific config:

```
VITE_API_URL=https://api.production.com
```

Access in code:
```typescript
const API_URL = import.meta.env.VITE_API_URL;
```

### Serving Static Files

The `dist/` directory contains static files that can be served by:
- Nginx
- Apache
- AWS S3 + CloudFront
- Vercel
- Netlify

Configure your server to:
1. Serve `index.html` for all routes (SPA routing)
2. Set proper cache headers for assets
3. Enable gzip/brotli compression

## Contributing

### Code Style

- Use TypeScript strict mode
- Follow React hooks rules
- Use functional components only
- Keep components focused and small
- Use descriptive variable names

### Testing Requirements

- All new components must have tests
- Test user interactions, not implementation
- Mock external dependencies (API calls)
- Aim for >80% code coverage

### Pull Request Process

1. Create feature branch
2. Implement changes with tests
3. Run `npm run test` and `npm run build`
4. Update documentation
5. Submit PR with clear description

## License

[Your License Here]

## Support

For issues and questions:
- **Bug Reports**: [GitHub Issues](https://github.com/tidemark-security/intercept/issues)
- **Documentation**: [Wiki](https://github.com/tidemark-security/intercept/wiki)
- **Discussions**: [GitHub Discussions](https://github.com/tidemark-security/intercept/discussions)
