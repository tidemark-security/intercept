# Intercept Backend API

FastAPI-based backend for the Intercept security case management platform.

## Tech Stack

- **Python**: 3.12+
- **Framework**: FastAPI 0.104+
- **ORM**: SQLModel 0.0.14+
- **Database**: PostgreSQL 14+ (async via asyncpg)
- **Migrations**: Alembic
- **Authentication**: Username/password with Argon2id hashing
- **Session Management**: Database-backed sessions with HTTP-only cookies
- **Testing**: pytest with AsyncClient

## Prerequisites

1. **Conda Environment**: Activate the project environment
   ```bash
   conda activate intercept
   ```

2. **PostgreSQL**: Running instance (via Docker Compose recommended)
   ```bash
   cd dev && docker compose up postgres -d
   ```

3. **Environment Variables**: Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

   Required variables:
   - `DATABASE_URL`: PostgreSQL connection string
   - `SESSION_SECRET_KEY`: Random secret for session signing
   - `SESSION_COOKIE_NAME`: Cookie name (default: `intercept_session`)
   - `SESSION_IDLE_TIMEOUT_HOURS`: Session timeout (1 for admin, 12 for analyst)
  - `RESET_TOKEN_EXPIRY_MINUTES`: Minutes before an admin-issued password setup/reset link expires

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Database Migrations

```bash
# Check current migration status
alembic current

# Apply all pending migrations
alembic upgrade head

# Create new migration (after model changes)
alembic revision --autogenerate -m "description"
```

### 3. Seed Initial Admin User

```bash
python scripts/seed_test_users.py
```

This creates three weak-password test accounts only when `INTERCEPT_ALLOW_TEST_USER_SEEDING=true` is set. Existing users are left unchanged.

### 4. Seed Link Templates (Optional)

```bash
python scripts/seed_link_templates.py
```

This populates the database with default link template configurations for:
- Email and phone links
- Microsoft Teams chat/call integrations
- Slack direct messaging
- CMDB and user directory lookups
- Threat intelligence searches (VirusTotal, etc.)

Templates can be customized later through the admin UI or directly in the database.

## Running the Server

### Development Mode

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **OpenAPI Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **MCP Server**: http://localhost:8000/mcp/streamable/

### Production Mode

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Authentication System

### Overview

The authentication system provides secure username/password authentication with:
- **Password Security**: Argon2id hashing (m=19456 KiB, t=2, p=1)
- **Session Management**: Database-backed sessions with HTTP-only cookies
- **Account Lockout**: Progressive rate limiting (5 failed attempts = 15 min lockout)
- **Password Policy**: 12+ chars with uppercase, lowercase, number, special character
- **Audit Logging**: All authentication events logged with correlation IDs

### User Roles

- **ADMIN**: Full system access, can manage users and reset passwords
- **ANALYST**: Standard case management access
- **AUDITOR**: Read-only access for compliance/security reviews

### Authentication Endpoints

#### Login
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "analyst",
  "password": "password123"
}

Response: 200 OK (sets session cookie)
{
  "user": {
    "id": "uuid",
    "username": "analyst",
    "role": "ANALYST",
    "status": "ACTIVE"
  },
  "session": {
    "id": "uuid",
    "expiresAt": "2025-10-13T12:00:00Z"
  }
}
```

#### Logout
```bash
POST /api/v1/auth/logout
Cookie: intercept_session=<session_id>

Response: 204 No Content
```

#### Session Validation
```bash
GET /api/v1/auth/session
Cookie: intercept_session=<session_id>

Response: 200 OK
{
  "user": {...},
  "session": {...},
  "mustChangePassword": false
}
```

#### Change Password (Voluntary)
```bash
POST /api/v1/auth/password/change
Cookie: intercept_session=<session_id>
Content-Type: application/json

{
  "currentPassword": "oldpass123",
  "newPassword": "NewSecurePass456!"
}

Response: 204 No Content
```

### Admin Endpoints

#### Create User
```bash
POST /api/v1/admin/auth/users
Cookie: intercept_session=<admin_session_id>
Content-Type: application/json

{
  "username": "newuser",
  "email": "newuser@example.com",
  "role": "ANALYST",
  "temporaryPassword": "TempPass123!"
}

Response: 201 Created
{
  "id": "uuid",
  "username": "newuser",
  "role": "ANALYST",
  "status": "ACTIVE",
  "mustChangePassword": true
}
```

#### Reset Password
```bash
POST /api/v1/admin/auth/password-resets
Cookie: intercept_session=<admin_session_id>
Content-Type: application/json

{
  "userId": "uuid",
  "sendEmail": true
}

Response: 200 OK
{
  "temporaryPassword": "TempCred789!",
  "expiresAt": "2025-10-13T12:30:00Z"
}
```

#### Disable User
```bash
PUT /api/v1/admin/auth/users/{userId}/status
Cookie: intercept_session=<admin_session_id>
Content-Type: application/json

{
  "status": "DISABLED"
}

Response: 200 OK
```

## MCP Server (Model Context Protocol)

Intercept includes an MCP server that enables AI assistants and automation tools to interact with the platform through a standardized protocol.

### Overview

The MCP server exposes a small, reviewed set of workflow tools, allowing:
- **AI Assistants**: ChatGPT, Claude, etc. can interact with Intercept
- **Automation**: Scripts and workflows can manage cases programmatically
- **Integrations**: n8n, Zapier, and other platforms can connect via MCP

### Quick Start

1. Set `MCP_OAUTH_ENABLED=true` and configure the externally reachable
   `MCP_OAUTH_PUBLIC_BASE_URL`.
2. Point an OAuth-capable MCP client at
   `http://localhost:8000/mcp/streamable/` for direct backend development, or
   at the public reverse-proxy origin in Compose deployments.
3. Complete browser login. Alternatively, create an Intercept API key for an
   automation/NHI client and send it as a bearer token.

### Authentication

Human-operated clients use OAuth browser authentication. When Intercept OIDC is
enabled, FastMCP proxies that same Google Workspace, Microsoft Entra, or generic
OIDC configuration. Otherwise Intercept runs the local FastMCP OAuth provider.

Automation can use API keys:
- **Header**: `Authorization: Bearer {api_key}` or `X-API-Key: {api_key}`
- **Format**: `int_{random_string}`
- **Management**: Create/revoke via Settings → API Keys

### Available Tools

The purpose-built tools are `get_summary`, `list_work`, `find_related`,
`get_item`, `validate_mermaid`, `record_triage_decision`, and
`add_timeline_item`. Use a normal MCP SDK/client for initialize, tool discovery,
and invocation; the removed `/mcp/v1/tools/*` REST shim is not supported.

### Documentation

- **Integration Guide**: [docs/mcp/integration-guide.md](../docs/mcp/integration-guide.md)
- **Configuration**: [docs/mcp/configuration.md](../docs/mcp/configuration.md)
- **Tool Reference**: [docs/mcp/tool-reference.md](../docs/mcp/tool-reference.md)

### Security

- API keys are hashed (Argon2id) in the database
- Keys have expiration dates and can be revoked
- Local OAuth tokens are opaque and hashed; OIDC proxy state is encrypted
- All MCP requests are audited with user context
- Use NHI (Non-Human Identity) accounts for automation

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Authentication tests only
pytest tests/integration/auth/ tests/unit/services/test_auth_service.py

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With coverage report
pytest --cov=app --cov-report=html
```

### Test Database

Tests use a separate test database configured in `conftest.py`. The database is automatically created and torn down for each test session.

## Project Structure

```
backend/
├── db_migrations/                    # Database migrations
│   └── versions/               # Migration scripts
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── api/
│   │   ├── route_utils.py      # Session middleware, error handlers
│   │   └── routes/
│   │       ├── auth.py         # Authentication endpoints
│   │       └── admin_auth.py   # Admin user management endpoints
│   ├── core/
│   │   ├── config.py           # Configuration and settings
│   │   ├── database.py         # Database connection management
│   │   └── metrics.py          # Prometheus metrics
│   ├── models/
│   │   ├── models.py           # SQLModel database models
│   │   └── enums.py            # Shared enumerations
│   └── services/
│       ├── auth_service.py     # Authentication business logic
│       ├── admin_auth_service.py  # User management business logic
│       ├── audit_service.py    # Audit logging
│       ├── security/
│       │   └── password_hasher.py  # Argon2id password hashing
│       └── notifications/          # Notification package
├── scripts/
│   └── seed_test_users.py      # Seed initial admin account
└── tests/
    ├── conftest.py             # Test configuration and fixtures
    ├── fixtures/               # Test data factories
    ├── integration/            # Integration tests
    └── unit/                   # Unit tests
```

## Common Tasks

### Add a New Database Model

1. Define model in `app/models/models.py` using SQLModel
2. Generate migration: `alembic revision --autogenerate -m "add_model"`
3. Review generated migration in `db_migrations/versions/`
4. Apply migration: `alembic upgrade head`
5. Regenerate frontend types: `cd .. && ./scripts/generate-types.sh`

### Add a New API Endpoint

1. Define route in appropriate router (`app/api/routes/`)
2. Implement business logic in service layer (`app/services/`)
3. Add integration tests in `tests/integration/`
4. Regenerate frontend types: `cd .. && ./scripts/generate-types.sh`

### Update Password Hashing Parameters

Edit `app/services/security/password_hasher.py`:
```python
ph = PasswordHasher(
    time_cost=2,        # Iterations
    memory_cost=19456,  # KiB (19 MiB)
    parallelism=1,      # Threads
    hash_len=32,        # Output length
    salt_len=16         # Salt length
)
```

Note: Changing parameters requires rehashing all passwords on next login.

## Troubleshooting

### Database Connection Issues

**Symptom**: `asyncpg.exceptions.InvalidCatalogNameError`

**Solution**: Ensure PostgreSQL is running and database exists
```bash
cd dev && docker compose up postgres -d
# Wait for database to be ready
docker compose exec postgres psql -U intercept_user -c "SELECT 1"
```

### Migration Conflicts

**Symptom**: `alembic.util.exc.CommandError: Target database is not up to date`

**Solution**: Check migration status and resolve conflicts
```bash
# Check current version
alembic current

# View migration history
alembic history

# Downgrade if needed
alembic downgrade -1

# Reapply migrations
alembic upgrade head
```

### Session Cookie Issues

**Symptom**: Users logged out unexpectedly

**Solution**: Verify session configuration
- Check `SESSION_SECRET_KEY` hasn't changed
- Verify `SESSION_IDLE_TIMEOUT_HOURS` is appropriate
- Check database for expired sessions
- Ensure cookies are HTTP-only and Secure in production

### Account Lockout

**Symptom**: Cannot login after failed attempts

**Solution**: Admin can clear lockout via database
```sql
UPDATE user_accounts 
SET failed_login_attempts = 0, lockout_expires_at = NULL 
WHERE username = 'locked_user';
```

Or wait for lockout to expire (15 minutes by default).

### Admin Reset Links

**Symptom**: User cannot finish an admin-issued password setup or reset

**Solution**: Verify the reset link is still valid and the expiry setting is appropriate.
```bash
RESET_TOKEN_EXPIRY_MINUTES=30
```

Admins can also adjust `reset_token.expiry_minutes` from the settings UI.

## Security Considerations

### Password Storage
- Passwords hashed with Argon2id (OWASP recommended)
- Hashing wrapped in `asyncio.to_thread()` to avoid blocking
- Original passwords never logged or stored

### Session Management
- Sessions stored in database (not stateless JWTs)
- HTTP-only cookies prevent XSS attacks
- Secure flag enforced in production (HTTPS only)
- Idle timeout enforced server-side
- All sessions except current revoked on password change

### Rate Limiting
- Failed login attempts tracked per user
- Progressive lockout after 5 failed attempts (15 min)
- Account lockout events logged for security monitoring

### Audit Logging
- All authentication events logged with correlation IDs
- Logs include: user ID, timestamp, action, outcome, IP address
- Sensitive data (passwords, tokens) redacted from logs
- 90-day retention for audit events

## Monitoring & Observability

### Metrics

Prometheus metrics exposed at `/metrics`:

- `auth_login_success_total{role}`: Successful logins by role
- `auth_login_failure_total{role,reason}`: Failed login attempts
- `auth_lockout_total{role}`: Account lockouts
- `auth_logout_total{reason}`: Session terminations
- `auth_password_change_total{forced}`: Password changes
- `auth_admin_reset_total`: Admin-issued resets

### Structured Logging

All logs use structured JSON format:
```json
{
  "timestamp": "2025-10-13T10:00:00Z",
  "level": "INFO",
  "correlation_id": "uuid",
  "event_type": "login_success",
  "user_id": "uuid",
  "username": "analyst",
  "ip_address": "192.168.1.1"
}
```

### Health Checks

```bash
# Application health
GET /health

# Database connectivity
GET /health/db
```

## Contributing

### Code Style

- Follow PEP 8
- Use type hints for all functions
- Document public APIs with docstrings
- Keep functions small and focused

### Testing Requirements

- All new endpoints must have integration tests
- Business logic must have unit tests
- Minimum 80% code coverage
- Tests must be deterministic and isolated

### Pull Request Process

1. Create feature branch from `main`
2. Implement changes with tests
3. Run full test suite: `pytest`
4. Run linters: `ruff check . && mypy .`
5. Update documentation as needed
6. Submit PR with clear description

## License

[Your License Here]

## Support

For issues and questions:
- **Bug Reports**: [GitHub Issues](https://github.com/tidemark-security/intercept/issues)
- **Documentation**: [Wiki](https://github.com/tidemark-security/intercept/wiki)
- **Discussions**: [GitHub Discussions](https://github.com/tidemark-security/intercept/discussions)
