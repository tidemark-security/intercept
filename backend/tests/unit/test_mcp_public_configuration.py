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


def _exact_location_block(config: str, route: str) -> str:
    marker = f"location = {route} {{"
    start = config.index(marker)
    end = config.index("\n    }", start)
    return config[start:end]


def _prefix_location_block(config: str, route: str) -> str:
    markers = (f"location ^~ {route} {{", f"location {route} {{")
    start = next(
        (config.index(marker) for marker in markers if marker in config),
        None,
    )
    assert start is not None, f"prefix location {route} is not configured"
    end = config.index("\n    }", start)
    return config[start:end]


def _service_block(config: str, service: str) -> str:
    match = re.search(
        rf"^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-z0-9_-]+:|^volumes:|^networks:)",
        config,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"{service} service is not configured"
    return match.group("body")


def test_dev_mcp_oauth_uses_the_public_intercept_origin() -> None:
    assert _compose_value("dev/docker-compose.yml", "MCP_OAUTH_PUBLIC_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost:8080}"
    )
    assert _compose_value("dev/docker-compose.yml", "MCP_OAUTH_LOGIN_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost:8080}"
    )
    assert _compose_value(
        "dev/docker-compose.yml",
        "MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA",
    ) == "${MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA:-50}"
    assert (
        "MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA=50"
        in (PROJECT_ROOT / "dev/.env.example").read_text(encoding="utf-8")
    )


def test_quickstart_mcp_oauth_uses_the_frontend_origin() -> None:
    path = "docs/quickstart/docker-compose.yml"

    assert _compose_value(path, "MCP_OAUTH_PUBLIC_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"
    )
    assert _compose_value(path, "MCP_OAUTH_LOGIN_BASE_URL") == (
        "${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"
    )
    assert _compose_value(
        path,
        "MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA",
    ) == "${MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA:-50}"
    assert _compose_value(path, "CORS_ORIGINS") == (
        '["${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"]'
    )
    assert _compose_value(path, "OIDC_ALLOWED_REDIRECT_ORIGINS") == (
        '["${INTERCEPT_PUBLIC_ORIGIN:-http://localhost}"]'
    )
    assert (
        "# MCP_OAUTH_PENDING_AUTHORIZATION_PER_SOURCE_QUOTA=50"
        in (PROJECT_ROOT / "docs/quickstart/.env.example").read_text(
            encoding="utf-8"
        )
    )


def test_quickstart_https_cookie_security_is_operator_configurable() -> None:
    path = "docs/quickstart/docker-compose.yml"
    env_example = (PROJECT_ROOT / "docs/quickstart/.env.example").read_text(
        encoding="utf-8"
    )

    assert _compose_value(path, "SESSION_COOKIE_SECURE") == (
        "${SESSION_COOKIE_SECURE:-false}"
    )
    assert "# SESSION_COOKIE_SECURE=true" in env_example
    assert "Set this to true whenever INTERCEPT_PUBLIC_ORIGIN uses HTTPS" in env_example


def test_nginx_routes_mcp_and_oauth_discovery_before_the_frontend() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        mcp = _location_block(config, "/mcp/")
        discovery = _location_block(config, "/.well-known/")
        backend_proxy = (
            "proxy_pass http://backend-ingress:8000;"
            if relative_path == "dev/nginx.conf"
            else "proxy_pass $backend_upstream;"
        )

        assert config.index("location ^~ /mcp/") < config.index("location / {")
        assert config.index("location ^~ /.well-known/") < config.index(
            "location / {"
        )
        assert backend_proxy in mcp
        assert "proxy_request_buffering off;" in mcp
        assert "proxy_buffering off;" in mcp
        assert backend_proxy in discovery
        assert "proxy_buffering off;" not in discovery
        assert "legacy SSE" not in config

    production = (PROJECT_ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    api = _location_block(production, "/api/")
    assert production.index("location ^~ /api/") < production.index("location / {")
    assert "resolver 127.0.0.11" in production
    assert "set $backend_upstream http://backend:8000;" in production
    assert "proxy_pass $backend_upstream;" in api


def test_quickstart_bridges_internal_minio_urls_through_the_frontend() -> None:
    production = (PROJECT_ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    api = _location_block(production, "/api/")
    storage = _prefix_location_block(production, "/storage/")
    quickstart = (
        PROJECT_ROOT / "docs/quickstart/docker-compose.yml"
    ).read_text(encoding="utf-8")
    frontend = _service_block(quickstart, "frontend")

    assert _compose_value(
        "docs/quickstart/docker-compose.yml",
        "STORAGE_ENDPOINT",
    ) == "minio:9000"
    assert 'sub_filter "http://minio:9000/" "/storage/";' in api
    assert "proxy_set_header Accept-Encoding \"\";" in api
    assert "set $storage_upstream http://minio:9000;" in production
    assert "rewrite ^/storage/(.*)$ /$1 break;" in storage
    assert "proxy_pass $storage_upstream;" in storage
    assert "proxy_set_header Host minio:9000;" in storage
    assert "    networks:\n      - default\n      - ingress" in frontend


def test_compose_trusts_only_its_dedicated_operator_overridable_ingress() -> None:
    expectations = {
        "dev/docker-compose.yml": "172.31.250.0/24",
        "docs/quickstart/docker-compose.yml": "172.31.251.0/24",
    }

    for relative_path, default_subnet in expectations.items():
        compose = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        trusted_cidrs = _compose_value(relative_path, "HTTP_TRUSTED_PROXY_CIDRS")

        assert trusted_cidrs == (
            f'["${{INTERCEPT_INGRESS_SUBNET:-{default_subnet}}}"]'
        )
        assert (
            f"subnet: ${{INTERCEPT_INGRESS_SUBNET:-{default_subnet}}}" in compose
        )
        assert "10.0.0.0/8" not in trusted_cidrs
        assert "172.16.0.0/12" not in trusted_cidrs
        assert "192.168.0.0/16" not in trusted_cidrs

    development_nginx = (
        PROJECT_ROOT / "dev/nginx.conf"
    ).read_text(encoding="utf-8")
    assert "proxy_pass http://backend:8000;" not in development_nginx
    assert "proxy_pass http://backend-ingress:8000;" in development_nginx


def test_dev_compose_passes_effective_credentials_to_public_exposure_guard() -> None:
    compose = (PROJECT_ROOT / "dev/docker-compose.yml").read_text(encoding="utf-8")
    backend = _service_block(compose, "backend")

    assert '      INTERCEPT_DEV_COMPOSE: "true"' in backend
    for variable in (
        "POSTGRES_PASSWORD",
        "LANGFLOW_DB_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "LANGFLOW_SUPERUSER_PASSWORD",
        "LANGFLOW_SECRET_KEY",
        "LANGFLOW_API_KEY",
        "SECRET_KEY",
        "INITIAL_ADMIN_PASSWORD",
    ):
        assert f"      {variable}:" in backend


def test_nginx_bounds_and_rate_limits_dynamic_registration_by_direct_peer() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "limit_req_zone $binary_remote_addr" in config
        for registration_path in ("/mcp/register", "/mcp/register/"):
            registration = _exact_location_block(config, registration_path)
            assert "client_max_body_size 64k;" in registration
            assert "limit_req zone=mcp_registration_per_ip" in registration
            assert "limit_req_status 429;" in registration
            assert "proxy_request_buffering on;" in registration
        assert "$http_x_forwarded_for zone=mcp_registration_per_ip" not in config


def test_nginx_rate_limits_mcp_authorization_by_direct_peer() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "limit_req_zone $binary_remote_addr "
            "zone=mcp_authorization_per_ip:10m" in config
        )
        for authorization_path in ("/mcp/authorize", "/mcp/authorize/"):
            authorization = _exact_location_block(config, authorization_path)
            assert "client_max_body_size 64k;" in authorization
            assert "limit_req zone=mcp_authorization_per_ip" in authorization
            assert "limit_req_status 429;" in authorization
            assert "proxy_pass " in authorization
            assert "proxy_request_buffering off;" in authorization
        assert "$http_x_forwarded_for zone=mcp_authorization_per_ip" not in config


def test_nginx_bounds_and_buffers_public_mcp_oauth_forms() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for oauth_form_path in (
            "/mcp/consent",
            "/mcp/consent/",
            "/mcp/token",
            "/mcp/token/",
            "/mcp/revoke",
            "/mcp/revoke/",
        ):
            oauth_form = _exact_location_block(config, oauth_form_path)
            assert "client_max_body_size 64k;" in oauth_form
            assert "limit_req zone=application_requests_per_ip" in oauth_form
            assert "limit_req_status 429;" in oauth_form
            assert "proxy_pass " in oauth_form
            assert "proxy_request_buffering on;" in oauth_form


def test_nginx_rate_limits_main_oidc_browser_flow_by_direct_peer() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "limit_req_zone $binary_remote_addr zone=oidc_login_per_ip:10m"
            in config
        )
        for route in (
            "/api/v1/auth/oidc/login",
            "/api/v1/auth/oidc/callback",
        ):
            oidc_flow = _exact_location_block(config, route)
            assert "limit_req zone=oidc_login_per_ip" in oidc_flow
            assert "limit_req_status 429;" in oidc_flow
        assert "$http_x_forwarded_for zone=oidc_login_per_ip" not in config


def test_nginx_bounds_and_rate_limits_passkey_ceremonies_by_direct_peer() -> None:
    routes = (
        "/api/v1/auth/passkeys/register/options",
        "/api/v1/auth/passkeys/register/options/",
        "/api/v1/auth/passkeys/register/verify",
        "/api/v1/auth/passkeys/register/verify/",
        "/api/v1/auth/passkeys/authenticate/options",
        "/api/v1/auth/passkeys/authenticate/options/",
        "/api/v1/auth/passkeys/authenticate/verify",
        "/api/v1/auth/passkeys/authenticate/verify/",
    )
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "limit_req_zone $binary_remote_addr zone=passkey_ceremony_per_ip:10m"
            in config
        )
        for route in routes:
            ceremony = _exact_location_block(config, route)
            assert "client_max_body_size 256k;" in ceremony
            assert "limit_req zone=passkey_ceremony_per_ip" in ceremony
            assert "limit_req_status 429;" in ceremony
            assert "proxy_request_buffering on;" in ceremony
        assert "$http_x_forwarded_for zone=passkey_ceremony_per_ip" not in config


def test_nginx_bounds_and_rate_limits_password_routes_by_direct_peer() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "limit_req_zone $binary_remote_addr zone=password_login_per_ip:10m"
            in config
        )
        for route in (
            "/api/v1/auth/login",
            "/api/v1/auth/login/",
            "/api/v1/auth/password/change",
            "/api/v1/auth/password/change/",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/reset-password/",
        ):
            login = _exact_location_block(config, route)
            assert "client_max_body_size 8k;" in login
            assert "limit_req zone=password_login_per_ip" in login
            assert "limit_req_status 429;" in login
            assert "proxy_request_buffering on;" in login
        assert "$http_x_forwarded_for zone=password_login_per_ip" not in config


def test_nginx_rate_limits_general_api_and_mcp_requests_by_direct_peer() -> None:
    for relative_path in ("dev/nginx.conf", "frontend/nginx.conf"):
        config = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "limit_req_zone $binary_remote_addr zone=application_requests_per_ip:10m"
            in config
        )
        for route in ("/api/", "/mcp/"):
            location = _prefix_location_block(config, route)
            assert "limit_req zone=application_requests_per_ip" in location
            assert "limit_req_status 429;" in location
        assert "$http_x_forwarded_for zone=application_requests_per_ip" not in config


def test_mcp_settings_explain_that_changes_require_a_restart() -> None:
    for key in (
        "mcp.oauth.enabled",
        "mcp.oauth.public_base_url",
        "mcp.oauth.login_base_url",
        "mcp.oauth.refresh_token_ttl_days",
        "mcp.oauth.access_token_ttl_seconds",
        "mcp.oauth.registration_max_body_bytes",
        "mcp.oauth.registration_pending_quota",
        "mcp.oauth.registration_total_quota",
        "mcp.oauth.registration_per_ip_quota",
        "mcp.oauth.registration_rate_window_seconds",
        "mcp.oauth.registration_abandoned_ttl_seconds",
        "mcp.oauth.registration_active_ttl_seconds",
        "mcp.oauth.pending_authorization_global_quota",
        "mcp.oauth.pending_authorization_per_client_quota",
        "mcp.oauth.pending_authorization_per_source_quota",
        "mcp.oauth.cimd_fetch_reservation_ttl_seconds",
        "mcp.oauth.cimd_cache_max_entries",
        "mcp.oauth.client_assertion_replay_global_quota",
        "mcp.oauth.client_assertion_replay_per_client_quota",
    ):
        assert "restart" in SETTINGS_REGISTRY[key].description.lower()


def test_mcp_sdk_has_principal_binding_security_floor() -> None:
    requirements = (
        PROJECT_ROOT / "backend/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()

    assert "mcp==1.27.2" in requirements
