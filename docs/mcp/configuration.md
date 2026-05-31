# MCP Server Configuration Guide

## Overview

This guide covers configuration options for the Tidemark Intercept MCP server, including environment variables, deployment options, and security settings.

The MCP server provides 7 purpose-built tools for AI agent integration. The preferred transport is Streamable HTTP at `/mcp/streamable/`, with legacy SSE still available at `/mcp/sse`.

Authentication supports two paths:

- OAuth 2.1 authorization-code with PKCE for human-operated local agents such as Codex or Claude Code.
- API keys for machine-to-machine integrations and non-human identity accounts.

## MCP Server Architecture

The MCP server is **not** auto-generated from FastAPI routes. Instead, it provides 7 intentionally designed tools:

| Tool | Purpose | Read-Only |
|------|---------|-----------|
| `get_summary` | Bounded context retrieval for alerts/cases/tasks | Yes |
| `list_work` | Global work discovery with filtering | Yes |
| `find_related` | Similarity search across entities | Yes |
| `record_triage_decision` | Record AI triage recommendations | No |
| `add_timeline_item` | Append notes to timelines | No |
| `get_item` | Retrieve full content of truncated items | Yes |
| `validate_mermaid` | Validate Mermaid diagram syntax with Mermaid parser script | Yes |

## Mermaid Validation Runtime

The `validate_mermaid` tool shells out to a local Node-based parser script (`scripts/mermaid-validator/validate_mermaid_syntax.mjs`).

- Backend Docker images install Node.js and parser dependencies under `/opt/mermaid-validator`.
- Non-Docker environments must provide `node` on `PATH` and install validator dependencies from `backend/scripts/mermaid-validator/package.json`.
- If parser dependencies are unavailable or the script cannot run correctly, the tool returns an operational error instead of a syntax-validation result.

## Environment Variables

The MCP server inherits configuration from the main Intercept application.

### Core Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | - | Yes |
| `SECRET_KEY` | Encryption key for secrets | - | Yes |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `CORS_ORIGINS` | Allowed CORS origins | `["*"]` | No |

### MCP OAuth Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MCP_OAUTH_ENABLED` | Enables OAuth 2.1 with PKCE for MCP browser sign-in | `false` | No |
| `MCP_OAUTH_PUBLIC_BASE_URL` | Public backend base URL used as the OAuth issuer and discovery URL | - | Yes, when OAuth is enabled |
| `MCP_OAUTH_LOGIN_BASE_URL` | Frontend base URL for local Intercept login during browser authorization | Same as `MCP_OAUTH_PUBLIC_BASE_URL` | No |
| `MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS` | OAuth access-token lifetime | `3600` | No |
| `MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS` | OAuth refresh-token lifetime | `30` | No |

### Example `.env` File

```bash
# Core settings
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/intercept
SECRET_KEY=your-secret-key-here-minimum-32-chars

# Logging
LOG_LEVEL=INFO

# CORS (adjust for production)
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]

# MCP OAuth browser auth for human-operated agents
MCP_OAUTH_ENABLED=true
MCP_OAUTH_PUBLIC_BASE_URL=http://localhost:8000
MCP_OAUTH_LOGIN_BASE_URL=http://localhost:5173
```

## MCP Endpoints

The MCP server exposes both the preferred streamable transport and the legacy SSE transport:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp/streamable/` | GET, POST | Preferred Streamable HTTP endpoint for modern MCP clients and Langflow |
| `/mcp/sse` | GET | Legacy SSE connection endpoint |
| `/mcp/messages` | POST | Legacy SSE message endpoint |

MCP requests accept either API key authentication via `Authorization: Bearer <key>` or `X-API-Key`, or OAuth bearer tokens issued through the MCP OAuth flow.

When OAuth is enabled and an MCP client sends no credential, Intercept returns a `WWW-Authenticate` challenge with the MCP protected-resource metadata URL. OAuth-capable MCP clients use that metadata to discover the authorization server, open the user's browser, and complete PKCE authorization.

## OAuth Browser Authorization

Use OAuth for human-to-machine access where the MCP client runs locally for a signed-in analyst.

1. Enable `MCP_OAUTH_ENABLED`.
2. Set `MCP_OAUTH_PUBLIC_BASE_URL` to the externally reachable backend origin, for example `https://intercept.example.com` or `http://localhost:8000` for local development.
3. Set `MCP_OAUTH_LOGIN_BASE_URL` to the frontend origin if it differs from the backend, for example `http://localhost:5173` in dev or `http://localhost` in quickstart.
4. Configure the MCP client with the MCP URL, for example `http://localhost:8000/mcp/streamable/`.
5. The client discovers OAuth metadata, opens the browser, and the user signs in with normal Intercept auth.

Supported OAuth capabilities:

- Dynamic client registration at `/oauth/register`
- Authorization endpoint at `/oauth/authorize`
- Token endpoint at `/oauth/token`
- Revocation endpoint at `/oauth/revoke`
- Public clients only: `token_endpoint_auth_method=none`
- Authorization code + PKCE only: `response_type=code`, `code_challenge_method=S256`
- Scope: `mcp:access`
- Loopback redirect URIs only, such as `http://127.0.0.1:49152/callback`

Users can review and revoke connected MCP clients from their profile page. Revocation invalidates active access and refresh tokens for that user/client pair.

## Deployment Options

The MCP server deploys alongside the backend app. For OAuth, make sure the public backend URL is stable and HTTPS in production, and that the frontend login URL can redirect back to the backend authorization URL through the `next` parameter.

## API Key Management

### Creating API Keys

#### For Human Users (Web UI)

1. Log in to Tidemark Intercept
2. Navigate to **Settings** → **API Keys**
3. Click **Create API Key**
4. Fill in the details:
   - **Name**: Descriptive name (e.g., "Claude Desktop", "Automation Script")
   - **Expiration**: Set an expiration date (recommended: 90 days)
5. Click **Create**
6. **Important**: Copy the API key immediately - it won't be shown again!

The API key format is: `int_{random_string}`

#### For NHI Accounts (Admin API)

```bash
# Create NHI account with API key
curl -X POST http://localhost:8000/api/v1/admin/auth/users/nhi \
  -H "Content-Type: application/json" \
  -H "Cookie: intercept_session=admin-session" \
  -d '{
    "username": "automation_service",
    "role": "ANALYST",
    "description": "Automated case management",
    "initial_api_key_name": "Service Key",
    "initial_api_key_expires_at": "2027-01-01T00:00:00Z"
  }'
```

### Key Rotation

Recommended rotation schedule:
- **Development**: 30 days
- **Production**: 90 days
- **Service accounts**: 90-180 days with monitoring

Rotation process:
1. Create new API key
2. Update client configuration
3. Test new key
4. Revoke old key
5. Monitor for errors

### Key Revocation

#### Via API

```bash
curl -X DELETE http://localhost:8000/api/v1/api-keys/{key_id} \
  -H "Cookie: intercept_session=admin-session"
```

#### Emergency Revocation

If a key is compromised:

1. **Immediate**: Revoke via API or database
2. **Database**: `UPDATE api_keys SET revoked_at = NOW() WHERE id = '{key_id}'`
3. **Monitor**: Check audit logs for unauthorized usage
4. **Notify**: Alert security team

## Monitoring

### Logging

MCP requests are logged with:
- User ID
- Authentication type (API key or OAuth)
- OAuth client name and ID when applicable
- Tool name
- Timestamp
- Status

**Log Location**: Standard application logs

**Example Log Entry**:
```
2026-01-12 10:30:15 - INFO - MCP auth success: user=automation_bot, user_id=abc-123, path=/mcp/streamable/, ip=10.0.0.1
```

### Metrics

Key metrics to track:

- **Authentication**:
  - API key validations per minute
  - OAuth token validations per minute
  - Authentication failures
  - Expired/revoked key or token attempts

- **Tool Usage**:
  - Tool calls per minute
  - Most used tools
  - Average response time
  - Error rate by tool

- **Performance**:
  - P50/P95/P99 latency
  - Database connection pool usage

### Alerts

Recommended alerts:

1. **High Authentication Failure Rate**
   - Threshold: > 10% of requests in 5 minutes
   - Action: Check for brute force attacks

2. **High Error Rate**
   - Threshold: > 5% of tool calls in 5 minutes
   - Action: Check application logs

3. **Slow Response Times**
   - Threshold: P95 > 1 second
   - Action: Check database performance

4. **Expired Key Usage**
   - Threshold: Any attempt with expired key
   - Action: Notify key owner

## Troubleshooting

### MCP Server Not Starting

**Symptom**: Backend starts but MCP endpoints return 404

**Checks**:
1. Verify FastMCP is installed: `pip list | grep fastmcp`
2. Check logs for MCP initialization errors
3. Verify `/mcp` mount point in app startup

**Solution**:
```bash
# Reinstall dependencies
cd backend
pip install -r requirements.txt

# Restart
uvicorn app.main:app --reload
```

### Authentication Always Fails

**Symptom**: All API keys or OAuth tokens are rejected with 401

**Checks**:
1. Verify SECRET_KEY is set correctly
2. Check database connectivity
3. Verify API key table exists
4. Check API key service initialization
5. If using OAuth, verify `MCP_OAUTH_PUBLIC_BASE_URL` exactly matches the MCP resource URL used by the client

**Solution**:
```bash
# Check database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM api_keys;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM mcp_oauth_tokens;"

# Verify encryption service
# Check logs for "Initializing encryption service..." message
```

### OAuth Browser Opens the Wrong Login URL

**Symptom**: The MCP client opens a browser, but `/login` is served by the backend or returns 404.

**Checks**:
1. Confirm `MCP_OAUTH_PUBLIC_BASE_URL` points to the backend/OAuth issuer origin.
2. Confirm `MCP_OAUTH_LOGIN_BASE_URL` points to the frontend origin.
3. Confirm the frontend allows redirecting back to the backend origin through the `next` parameter.

**Solution**: Set both URLs explicitly when frontend and backend run on different origins:

```bash
MCP_OAUTH_PUBLIC_BASE_URL=http://localhost:8000
MCP_OAUTH_LOGIN_BASE_URL=http://localhost:5173
```

### SSE Connection Drops

**Symptom**: MCP connections disconnect unexpectedly

**Checks**:
1. Verify nginx/proxy SSE configuration
2. Check `proxy_read_timeout` is high enough
3. Ensure `proxy_buffering off` is set

**Solution**: Update proxy/load balancer configuration for SSE support

## Next Steps

- Review [Integration Guide](./integration-guide.md) for client setup
- See [Tool Reference](./tool-reference.md) for complete tool documentation
