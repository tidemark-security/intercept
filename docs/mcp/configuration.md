# MCP Server Configuration Guide

## Overview

Intercept exposes one FastMCP Streamable HTTP resource at
`/mcp/streamable/`. Human users authenticate through OAuth in the browser;
automation and non-human identities can continue to use Intercept API keys.

There is no SSE transport and no legacy `/oauth/*` API. OAuth discovery,
registration, authorization, token exchange, and revocation are served by
FastMCP's native routes.

## Authentication mode selection

Each backend worker resolves the database-backed Intercept settings once at
startup and builds an immutable FastMCP authentication topology:

| MCP OAuth | Intercept OIDC | MCP mode |
|---|---|---|
| Disabled | Any value | API keys only |
| Enabled | Disabled | Intercept local OAuth server |
| Enabled | Enabled and complete | OIDC proxy |
| Enabled | Enabled but incomplete | Startup/readiness failure |

In every OAuth mode, FastMCP `MultiAuth` also accepts Intercept API keys through
`Authorization: Bearer <key>` or `X-API-Key` when `Authorization` is absent.
Changing OIDC or MCP OAuth settings requires restarting every backend worker.

## Environment variables

These environment variables seed the corresponding settings. Values changed in
the Settings UI take precedence through Intercept's normal settings service.

| Variable | Description | Default |
|---|---|---|
| `MCP_OAUTH_ENABLED` | Enable browser OAuth; `false` is the API-key-only kill switch | `false` |
| `MCP_OAUTH_PUBLIC_BASE_URL` | Externally reachable Intercept origin used for MCP and OAuth | Required when OAuth is enabled |
| `MCP_OAUTH_LOGIN_BASE_URL` | Public UI origin for local login when it differs from the MCP origin | Public base URL |
| `MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS` | MCP access-token lifetime | `3600` |
| `MCP_OAUTH_REFRESH_TOKEN_TTL_DAYS` | MCP refresh-token lifetime | `30` |

The public and login values must be origins with no path, query, fragment, or
credentials. HTTPS is required except for `localhost` and other loopback
addresses.

For the development Compose stack, set one public boundary and let Compose share
it with the backend:

```bash
INTERCEPT_PUBLIC_ORIGIN=http://localhost:8080
MCP_OAUTH_ENABLED=true
```

Then configure the client with:

```text
http://localhost:8080/mcp/streamable/
```

## Routes

| Purpose | Route |
|---|---|
| MCP resource | `/mcp/streamable/` |
| Authorization | `/mcp/authorize` |
| Token exchange | `/mcp/token` |
| Dynamic client registration | `/mcp/register` |
| Revocation | `/mcp/revoke` |
| Upstream OIDC callback | `/mcp/auth/callback` |
| Protected-resource metadata | `/.well-known/oauth-protected-resource/mcp/streamable` |
| Authorization-server metadata | `/.well-known/oauth-authorization-server/mcp` |
| Local consent | `/api/v1/mcp/oauth/consent/{request_id}` |

The outer ASGI application serves discovery first, mounts FastMCP at `/mcp`,
and places the existing FastAPI application last. A reverse proxy must likewise
route `/mcp/` and `/.well-known/` before its SPA fallback. Disable buffering for
`/mcp/`; discovery responses should use normal buffering.

## OIDC proxy mode

When Intercept OIDC is enabled, MCP reuses the same discovery URL, client ID,
client secret, scopes, account-linking policy, JIT policy, and role mapping as
web login. Register this additional redirect URI in the same Google Workspace,
Microsoft Entra, or generic OIDC application:

```text
${MCP_OAUTH_PUBLIC_BASE_URL}/mcp/auth/callback
```

The client-facing scope is always `mcp:access`. Intercept translates it to the
configured upstream OIDC scopes and never sends `mcp:access` to the identity
provider. Google requests offline consent; Entra includes `offline_access`.
Upstream tokens are never returned to the MCP client.

## Local OAuth mode

When Intercept OIDC is disabled, FastMCP provides OAuth discovery, dynamic
client registration, S256 PKCE, token exchange, refresh, and revocation. The
browser is sent through normal Intercept login and a CSRF-protected consent
screen. Authorization codes are one-use, refresh tokens rotate, and replay
revokes the whole token family.

Users can review and revoke grants in **Profile → Connected MCP Clients**.

## Native OAuth storage

OIDC proxy state is stored by `py-key-value-aio`'s native PostgreSQL backend in
the Alembic-managed `fastmcp_oauth_kv` table. Payloads are wrapped with native
Fernet encryption. The runtime uses `auto_create=False`; a missing table or a
storage encryption-key mismatch fails startup clearly.

JWT signing and storage encryption keys are independently derived from
`SECRET_KEY`. Every replica therefore needs the same `SECRET_KEY`. Do not query
or edit the FastMCP JSON payloads as application data; connected-client views
use a separate token-free relational projection.

## API keys

Create keys in **Settings → API Keys** or create a dedicated NHI account through
the admin API. Copy a newly created key immediately because it is only shown
once. Example client configuration:

```json
{
  "mcpServers": {
    "intercept": {
      "url": "http://localhost:8080/mcp/streamable/",
      "headers": {
        "Authorization": "Bearer int_your_api_key_here"
      }
    }
  }
}
```

API-key and OAuth principals both reload the local user on every MCP request.
Inactive or deleted users are rejected, and auditor write restrictions apply to
both authentication methods.

## Troubleshooting

### Browser or client discovers an internal port

Fetch the advertised metadata through the same origin used by the MCP client:

```bash
curl -i http://localhost:8080/.well-known/oauth-protected-resource/mcp/streamable
```

It must return JSON and contain only the external origin. If it returns frontend
HTML, fix the reverse-proxy route order. If it contains another port, correct
`INTERCEPT_PUBLIC_ORIGIN`/`MCP_OAUTH_PUBLIC_BASE_URL` and restart all backend
workers.

### OIDC startup fails

An enabled OIDC configuration must include a valid HTTPS discovery URL, client
ID, and client secret. Intercept deliberately does not fall back to local auth
when an enabled OIDC configuration is incomplete. Use
`MCP_OAUTH_ENABLED=false` as the API-key-only recovery switch, or complete the
OIDC configuration and restart.

### Existing experimental credentials stop working

The native-auth migration revokes pre-native MCP authorization codes, tokens,
and consents. Reconnect the MCP client and complete browser authorization again.

## Related documentation

- [Integration Guide](./integration-guide.md)
- [Tool Reference](./tool-reference.md)
