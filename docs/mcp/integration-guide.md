# MCP Integration Guide

## Overview

The Tidemark Intercept MCP (Model Context Protocol) server enables AI assistants, automation tools, and custom applications to interact with the case management platform through a standardized protocol.

The MCP server provides **7 purpose-built tools** designed for AI agent workflows:
- Read operations: `get_summary`, `list_work`, `find_related`, `get_item`, `validate_mermaid`
- Write operations: `record_triage_decision`, `add_timeline_item`

**MCP URL**: `http://localhost:8000/mcp/sse`

## Prerequisites

- Tidemark Intercept backend running
- User account with appropriate permissions
- API key for authentication
- MCP client (Claude Desktop, custom client, etc.)

## Setup

### 1. Create an API Key

API keys are required for MCP authentication. You can create them via the web interface or API.

#### Via Web Interface

1. Log in to Tidemark Intercept
2. Navigate to **Settings** → **API Keys**
3. Click **Create API Key**
4. Fill in the details:
   - **Name**: Descriptive name (e.g., "Claude Desktop", "Triage Agent")
   - **Expiration**: Set an expiration date (recommended: 90 days)
5. Click **Create**
6. **Important**: Copy the API key immediately - it won't be shown again!

The API key format is: `int_{random_string}`

#### Via API (Admin)

For NHI (Non-Human Identity) accounts:

```bash
curl -X POST http://localhost:8000/api/v1/admin/auth/users/nhi \
  -H "Content-Type: application/json" \
  -H "Cookie: intercept_session=your-session-cookie" \
  -d '{
    "username": "triage_agent",
    "role": "ANALYST",
    "description": "AI triage agent for alert processing",
    "initial_api_key_name": "Triage Agent Key",
    "initial_api_key_expires_at": "2027-01-01T00:00:00Z"
  }'
```

Response includes the API key (one-time only):

```json
{
  "user": {...},
  "api_key": {
    "key": "int_abc123...",
    "id": "uuid",
    "name": "Triage Agent Key",
    "expires_at": "2027-01-01T00:00:00Z"
  }
}
```

### 2. Configure Your MCP Client

#### Claude Desktop

Add to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "intercept": {
      "url": "http://localhost:8000/mcp/sse",
      "headers": {
        "Authorization": "Bearer int_your_api_key_here"
      }
    }
  }
}
```

Restart Claude Desktop after updating the configuration.

#### Other MCP Clients

Any MCP-compatible client can connect using:
- **URL**: `http://localhost:8000/mcp/sse`
- **Transport**: SSE (Server-Sent Events)
- **Authentication**: `Authorization: Bearer <api_key>` header

## Available Tools

The MCP server provides 7 intentionally designed tools:

### Read-Only Tools

| Tool | Purpose |
|------|---------|
| `get_summary` | Get bounded context for an alert, case, or task |
| `list_work` | List and filter alerts, cases, or tasks |
| `find_related` | Find similar/related items |
| `get_item` | Retrieve full content of truncated timeline items |
| `validate_mermaid` | Validate Mermaid diagram syntax before saving or sharing diagrams |

### Write Tools

| Tool | Purpose |
|------|---------|
| `record_triage_decision` | Record AI triage recommendation for an alert |
| `add_timeline_item` | Append notes to alert/case/task timelines |

## Common Integration Patterns

### Pattern 1: AI Triage Agent

Process new alerts and record triage recommendations:

```python
# 1. List new alerts
alerts = await mcp.call_tool("list_work", {
    "kind": "alert",
    "statuses": ["NEW"],
    "limit": 10
})

# 2. For each alert, get detailed context
for alert in alerts["items"]:
    summary = await mcp.call_tool("get_summary", {
        "kind": "alert",
        "id": alert["human_id"]
    })
    
    # 3. Find related alerts for context
    related = await mcp.call_tool("find_related", {
        "seed_kind": "alert",
        "seed_id": alert["human_id"],
        "max_matches": 5
    })
    
    # 4. Analyze and record triage decision
    await mcp.call_tool("record_triage_decision", {
        "alert_id": alert["human_id"],
        "disposition": "TRUE_POSITIVE",
        "confidence": 0.85,
        "reasoning_bullets": [
            "Source IP 10.0.0.1 has 5 similar alerts in past 24h",
            "Destination matches known C2 infrastructure"
        ],
        "suggested_priority": "HIGH",
        "commit": False  # Dry-run first
    })
```

### Pattern 2: Investigation Assistant

Help analysts investigate cases:

```python
# Get case context
case = await mcp.call_tool("get_summary", {
    "kind": "case",
    "id": "CAS-0000123",
    "max_timeline_items": 50,
    "max_observables": 30
})

# Add investigation notes
await mcp.call_tool("add_timeline_item", {
    "target_kind": "case",
    "target_id": "CAS-0000123",
    "item_id": f"note-{uuid4()}",
    "body": "Analysis of observables indicates lateral movement pattern...",
    "commit": True
})
```

### Pattern 3: Correlation Engine

Find and link related alerts:

```python
# Get an alert
alert = await mcp.call_tool("get_summary", {
    "kind": "alert",
    "id": "ALT-0000456"
})

# Find related items across all entity types
related = await mcp.call_tool("find_related", {
    "seed_kind": "alert",
    "seed_id": "ALT-0000456",
    "max_matches": 20
})

# Each match includes explainable reasons
for match in related["matches"]:
    print(f"{match['human_id']}: {match['why']}")
    # Output: "CAS-0000789: ['shared_ip:10.0.0.1', 'same_source_title']"

### Pattern 4: Diagram Validation

Validate Mermaid before persisting documentation or sending it to a frontend renderer:

```python
result = await mcp.call_tool("validate_mermaid", {
  "diagram": "graph TD\nA[Analyst] --> B[Case]"
})

if not result["valid"]:
  raise ValueError(result["errors"])
```
```

## Dry-Run Mode

Write tools (`record_triage_decision`, `add_timeline_item`) support dry-run mode:

```python
# Preview what would happen without committing
result = await mcp.call_tool("record_triage_decision", {
    "alert_id": "ALT-0000123",
    "disposition": "FALSE_POSITIVE",
    "confidence": 0.95,
    "commit": False  # Dry-run mode
})

print(result["mode"])  # "dry_run"
print(result["suggested_patches"])  # What would change

# If satisfied, commit the change
result = await mcp.call_tool("record_triage_decision", {
    "alert_id": "ALT-0000123",
    "disposition": "FALSE_POSITIVE",
    "confidence": 0.95,
    "commit": True  # Actually commit
})

print(result["mode"])  # "committed"
```

## ID Formats

All tools accept **forgiving ID formats**:

| Format | Example | Accepted |
|--------|---------|----------|
| Integer | `123` | ✅ |
| Human ID | `ALT-0000123` | ✅ |
| Human ID (no padding) | `ALT-123` | ✅ |
| String integer | `"123"` | ✅ |

```python
# All of these work for the same alert
await mcp.call_tool("get_summary", {"kind": "alert", "id": "123"})
await mcp.call_tool("get_summary", {"kind": "alert", "id": "ALT-0000123"})
await mcp.call_tool("get_summary", {"kind": "alert", "id": "ALT-123"})
```

## Error Handling

### Common Errors

**401 Unauthorized - Missing API Key**

```json
{
  "message": "API key required. Use Authorization: Bearer <key> or X-API-Key header."
}
```

**Solution**: Add Authorization header to your MCP client config

**401 Unauthorized - Invalid/Expired API Key**

```json
{
  "message": "Invalid API key"
}
```

**Solution**: Verify API key, check expiration date

**403 Forbidden - User Inactive**

```json
{
  "message": "User account is not active"
}
```

**Solution**: Check user status in admin panel

### Robust Error Handling

```python
async def call_tool_safe(mcp, tool_name: str, arguments: dict):
    """Call tool with error handling."""
    try:
        result = await mcp.call_tool(tool_name, arguments)
        return {"success": True, "data": result}
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            return {"success": False, "error": "Authentication failed - check API key"}
        elif "403" in error_msg:
            return {"success": False, "error": "Permission denied"}
        elif "404" in error_msg:
            return {"success": False, "error": "Entity not found"}
        else:
            return {"success": False, "error": error_msg}
```

## Security Best Practices

1. **Protect API Keys**
   - Never commit API keys to version control
   - Use environment variables or secure vaults
   - Rotate keys regularly (every 90 days recommended)

2. **Use NHI Accounts for Automation**
   - Create dedicated non-human accounts
   - Set appropriate role permissions
   - Monitor usage in audit logs

3. **Use Dry-Run Mode**
   - Always test write operations in dry-run mode first
   - Verify `suggested_patches` before committing

4. **Validate Input**
   - Sanitize data before sending to tools
   - Validate responses before using

5. **Monitor Usage**
   - Track API key usage
   - Alert on unusual patterns
   - Review audit logs regularly

## Performance Tips

1. **Use Bounded Queries**
   - `get_summary` returns bounded timeline items (default 25, max 50)
   - `list_work` has a max limit of 50 items per request
   - Use `cursor` for pagination when needed

2. **Incremental Refresh**
   - Use `since` parameter in `get_summary` to get only new items
   - Reduces response size for frequently polled entities

3. **Leverage Caching**
   - Tool schemas rarely change - cache the tools list
   - Cache lookup data (entity lists) with appropriate TTL

4. **Batch Operations**
   - Group related tool calls logically
   - Use pagination cursors efficiently

## Next Steps

- See [Tool Reference](./tool-reference.md) for complete tool documentation
- Read [Configuration Guide](./configuration.md) for deployment options
