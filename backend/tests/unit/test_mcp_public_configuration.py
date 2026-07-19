from __future__ import annotations

import re
from pathlib import Path

from app.core.settings_registry import SETTINGS_REGISTRY


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _compose_value(path: str, key: str) -> str:
    compose = (PROJECT_ROOT / path).read_text(encoding="utf-8")
    match = re.search(
        rf"^      {re.escape(key)}: (.+?)(?:\s+#.*)?$",
        compose,
        re.MULTILINE,
    )
    assert match is not None, f"{key} is not configured in {path}"
    return match.group(1).strip("\"'")


def _location_block(config: str, route: str) -> str:
    marker = f"location ^~ {route} {{"
    start = config.index(marker)
    end = config.index("\n    }", start)
    return config[start:end]


def test_dev_mcp_oauth_uses_the_public_intercept_origin() -> None:
    assert _compose_value("dev/docker-compose.yml", "MCP_OAUTH_PUBLIC_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost:8080}"
    )
    assert _compose_value("dev/docker-compose.yml", "MCP_OAUTH_LOGIN_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost:8080}"
    )


def test_quickstart_mcp_oauth_uses_the_frontend_origin() -> None:
    path = "docs/quickstart/docker-compose.yml"

    assert _compose_value(path, "MCP_OAUTH_PUBLIC_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"
    )
    assert _compose_value(path, "MCP_OAUTH_LOGIN_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"
    )
    assert _compose_value(path, "CORS_ORIGINS") == (
        '["${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"]'
    )
    assert _compose_value(path, "OIDC_ALLOWED_REDIRECT_ORIGINS") == (
        '["${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"]'
    )


def test_nginx_routes_mcp_and_oauth_discovery_before_the_frontend() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        mcp = _location_block(config, "/mcp/")
        discovery = _location_block(config, "/.well-known/")

        assert config.index("location ^~ /mcp/") < config.index("location / {")
        assert config.index("location ^~ /.well-known/") < config.index(
            "location / {"
        )
        assert "proxy_pass http://backend:8000;" in mcp
        assert "proxy_request_buffering off;" in mcp
        assert "proxy_buffering off;" in mcp
        assert "proxy_pass http://backend:8000;" in discovery
        assert "proxy_buffering off;" not in discovery
        assert "legacy SSE" not in config

    production = (PROJECT_ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    api = _location_block(production, "/api/")
    assert production.index("location ^~ /api/") < production.index("location / {")
    assert "proxy_pass http://backend:8000;" in api


def test_mcp_settings_explain_that_changes_require_a_restart() -> None:
    for key in (
        "mcp.oauth.enabled",
        "mcp.oauth.public_base_url",
        "mcp.oauth.login_base_url",
        "mcp.oauth.refresh_token_ttl_days",
        "mcp.oauth.access_token_ttl_seconds",
    ):
        assert "restart" in SETTINGS_REGISTRY[key].description.lower()
