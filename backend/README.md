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

This creates three test accounts:
- **admin/admin** (ADMIN role)
- **analyst/analyst** (ANALYST role)
- **auditor/auditor** (AUDITOR role)

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
- **MCP Server**: http://localhost:8000/mcp

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

The MCP server exposes all REST API endpoints as callable tools, allowing:
- **AI Assistants**: ChatGPT, Claude, etc. can interact with Intercept
- **Automation**: Scripts and workflows can manage cases programmatically
- **Integrations**: n8n, Zapier, and other platforms can connect via MCP

### Quick Start

1. **Create an API Key** (via web UI or admin API)
   ```bash
   # Create NHI account with API key
   POST /api/v1/admin/auth/users/nhi
   {
     "username": "automation_bot",
     "role": "ANALYST",
     "initial_api_key_name": "Bot Key",
     "initial_api_key_expires_at": "2026-01-01T00:00:00Z"
   }
   ```

2. **List Available Tools**
   ```bash
   curl -X POST http://localhost:8000/mcp/v1/tools/list \
     -H "Authorization: Bearer int_your_api_key_here"
   ```

3. **Call a Tool**
   ```bash
   curl -X POST http://localhost:8000/mcp/v1/tools/call \
     -H "Authorization: Bearer int_your_api_key_here" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "get_cases_api_v1_cases_get",
       "arguments": {"limit": 5, "status": ["NEW"]}
     }'
   ```

### Authentication

MCP endpoints require API key authentication:
- **Header**: `Authorization: Bearer {api_key}` or `X-API-Key: {api_key}`
- **Format**: `int_{random_string}`
- **Management**: Create/revoke via Settings → API Keys

### Available Tools

All REST API endpoints are automatically exposed as MCP tools. Tool names follow the pattern:
```
{function_name}_{path_with_underscores}_{http_method}
```

Examples:
- `get_cases_api_v1_cases_get` → GET /api/v1/cases
- `create_case_api_v1_cases_post` → POST /api/v1/cases
- `update_alert_api_v1_alerts` → PUT /api/v1/alerts/{alert_id}

### Integration Examples

**Python**:
```python
import httpx

async def get_cases(api_key: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/mcp/v1/tools/call",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": "get_cases_api_v1_cases_get",
                "arguments": {"limit": 10}
            }
        )
        return response.json()
```

**JavaScript**:
```javascript
const response = await fetch('http://localhost:8000/mcp/v1/tools/call', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'get_cases_api_v1_cases_get',
    arguments: { limit: 10 }
  })
});
```

### Documentation

- **Integration Guide**: [docs/mcp-integration-guide.md](../docs/mcp-integration-guide.md)
- **Configuration**: [docs/mcp-configuration.md](../docs/mcp-configuration.md)
- **Quick Start**: [specs/004-mcp-server-v1/quickstart.md](../specs/004-mcp-server-v1/quickstart.md)
- **Protocol Contract**: [specs/004-mcp-server-v1/contracts/mcp-protocol.md](../specs/004-mcp-server-v1/contracts/mcp-protocol.md)

### Security

- API keys are hashed (Argon2id) in the database
- Keys have expiration dates and can be revoked
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
