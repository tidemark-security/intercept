# MCP Server Configuration Guide

## Overview

This guide covers configuration options for the Tidemark Intercept MCP server, including environment variables, deployment options, and security settings.

The MCP server provides 7 purpose-built tools for AI agent integration, using Server-Sent Events (SSE) transport at `/mcp/sse`.

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

### Example `.env` File

```bash
# Core settings
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/intercept
SECRET_KEY=your-secret-key-here-minimum-32-chars

# Logging
LOG_LEVEL=INFO

# CORS (adjust for production)
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]
```

## MCP Endpoints

The MCP server exposes two endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp/sse` | GET | SSE connection for MCP protocol |
| `/mcp/messages` | POST | Message endpoint for MCP requests |

All requests require API key authentication via `Authorization: Bearer <key>` or `X-API-Key` header.

## Deployment Options

The MCP server deploys alongside the backend app - no special considerations are needed.

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
- User ID (from API key)
- Tool name
- Timestamp
- Status

**Log Location**: Standard application logs

**Example Log Entry**:
```
2026-01-12 10:30:15 - INFO - MCP auth success: user=automation_bot, user_id=abc-123, path=/mcp/sse, ip=10.0.0.1
```

### Metrics

Key metrics to track:

- **Authentication**:
  - API key validations per minute
  - Authentication failures
  - Expired/revoked key attempts

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

**Symptom**: All API keys rejected with 401

**Checks**:
1. Verify SECRET_KEY is set correctly
2. Check database connectivity
3. Verify API key table exists
4. Check API key service initialization

**Solution**:
```bash
# Check database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM api_keys;"

# Verify encryption service
# Check logs for "Initializing encryption service..." message
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
