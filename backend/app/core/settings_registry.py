"""
Declarative settings registry — single source of truth for all application settings.

Every setting in the system is declared here with its key, env var mapping,
type, default value, category, and whether it is local-only.

**Precedence chain** (highest wins):
    1. Environment variable
    2. .env file (resolved via Pydantic BaseSettings)
    3. Database (app_settings table) — skipped for local_only settings
    4. Default from this registry

**local_only** settings:
    - Never read from / written to the database
    - Cannot be changed at runtime via the admin API
    - Serve as a proxy for "not hot-swappable" (e.g. database URL, secret key,
      Argon2 params whose change would break existing hashes, CORS origins
      baked into middleware at startup, etc.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.models.enums import SettingType


@dataclass(frozen=True)
class SettingDefinition:
    """Metadata for a single application setting."""

    key: str
    """Dotted setting key, e.g. ``langflow.base_url``."""

    env_var: str
    """Environment variable name that maps to this key.

    Auto-derived from *key* as ``key.upper().replace('.', '__')`` unless
    explicitly overridden.
    """

    value_type: SettingType = SettingType.STRING
    """How to coerce the raw string value."""

    default: Any = None
    """Default value when neither env var, .env, nor DB provides one."""

    is_secret: bool = False
    """Whether the value should be masked in API responses and encrypted in DB."""

    local_only: bool = False
    """If True the setting is never stored in / read from the database.

    It can only be supplied via an environment variable or ``.env`` file.
    The admin API will expose it as read-only.
    """

    category: str = "general"
    """Grouping key used by the admin UI to organise settings into sections."""

    description: str = ""
    """Human-readable explanation shown in the admin UI."""


def _def(
    key: str,
    *,
    env_var: Optional[str] = None,
    value_type: SettingType = SettingType.STRING,
    default: Any = None,
    is_secret: bool = False,
    local_only: bool = False,
    category: str = "general",
    description: str = "",
) -> SettingDefinition:
    """Convenience factory that auto-derives *env_var* from *key*."""
    resolved_env_var = env_var or key.upper().replace(".", "__")
    return SettingDefinition(
        key=key,
        env_var=resolved_env_var,
        value_type=value_type,
        default=default,
        is_secret=is_secret,
        local_only=local_only,
        category=category,
        description=description,
    )


# ============================================================================
# Settings Registry
# ============================================================================
# Grouped by category.  local_only=True means env/.env only (no DB).

SETTINGS_REGISTRY: Dict[str, SettingDefinition] = {}


def _register(*defs: SettingDefinition) -> None:
    for d in defs:
        SETTINGS_REGISTRY[d.key] = d


# ---------------------------------------------------------------------------
# Bootstrap / infrastructure  (local_only — needed before DB is available)
# ---------------------------------------------------------------------------
_register(
    _def(
        "database.url",
        env_var="DATABASE_URL",
        local_only=True,
        is_secret=True,
        category="bootstrap",
        description="PostgreSQL connection string (asyncpg)",
        default="postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/intercept_case_db",
    ),
    _def(
        "secret_key",
        env_var="SECRET_KEY",
        local_only=True,
        is_secret=True,
        category="bootstrap",
        description="Application secret key for encryption and signing",
        default="your-super-secret-key-change-this-in-production",
    ),
    _def(
        "log_level",
        env_var="LOG_LEVEL",
        local_only=True,
        category="bootstrap",
        description="Python logging level (DEBUG, INFO, WARNING, ERROR)",
        default="INFO",
    ),
    _def(
        "cors_origins",
        env_var="CORS_ORIGINS",
        value_type=SettingType.JSON,
        local_only=True,
        category="bootstrap",
        description="Allowed CORS origins (JSON array)",
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
    ),
)

# ---------------------------------------------------------------------------
# Session / Cookie  (local_only — read per-request but from frozen singleton)
# ---------------------------------------------------------------------------
_register(
    _def(
        "auth.session.cookie_name",
        env_var="SESSION_COOKIE_NAME",
        local_only=True,
        category="session",
        description="Name of the session cookie",
        default="intercept_session",
    ),
    _def(
        "auth.session.cookie_domain",
        env_var="SESSION_COOKIE_DOMAIN",
        local_only=True,
        category="session",
        description="Domain attribute for the session cookie",
        default=None,
    ),
    _def(
        "auth.session.cookie_path",
        env_var="SESSION_COOKIE_PATH",
        local_only=True,
        category="session",
        description="Path attribute for the session cookie",
        default="/",
    ),
    _def(
        "auth.session.cookie_secure",
        env_var="SESSION_COOKIE_SECURE",
        value_type=SettingType.BOOLEAN,
        local_only=True,
        category="session",
        description="Whether the session cookie requires HTTPS",
        default=True,
    ),
    _def(
        "auth.session.cookie_http_only",
        env_var="SESSION_COOKIE_HTTP_ONLY",
        value_type=SettingType.BOOLEAN,
        local_only=True,
        category="session",
        description="Whether the session cookie is HTTP-only",
        default=True,
    ),
    _def(
        "auth.session.cookie_same_site",
        env_var="SESSION_COOKIE_SAME_SITE",
        local_only=True,
        category="session",
        description="SameSite attribute (lax, strict, none)",
        default="lax",
    ),
    _def(
        "auth.session.idle_timeout_hours",
        env_var="SESSION_IDLE_TIMEOUT_HOURS",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="session",
        description="Hours before an idle session expires",
        default=12,
    ),
    _def(
        "auth.session.absolute_timeout_hours",
        env_var="SESSION_ABSOLUTE_TIMEOUT_HOURS",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="session",
        description="Maximum session lifetime in hours regardless of activity",
        default=48,
    ),
)

# ---------------------------------------------------------------------------
# Argon2 password hashing  (local_only — changing breaks existing hashes)
# ---------------------------------------------------------------------------
_register(
    _def(
        "auth.argon2.time_cost",
        env_var="ARGON2_TIME_COST",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="argon2",
        description="Argon2 time cost parameter",
        default=2,
    ),
    _def(
        "auth.argon2.memory_cost_kib",
        env_var="ARGON2_MEMORY_COST_KIB",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="argon2",
        description="Argon2 memory cost in KiB",
        default=19_456,
    ),
    _def(
        "auth.argon2.parallelism",
        env_var="ARGON2_PARALLELISM",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="argon2",
        description="Argon2 parallelism factor",
        default=1,
    ),
    _def(
        "auth.argon2.hash_len",
        env_var="ARGON2_HASH_LEN",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="argon2",
        description="Argon2 hash length in bytes",
        default=32,
    ),
    _def(
        "auth.argon2.salt_len",
        env_var="ARGON2_SALT_LEN",
        value_type=SettingType.NUMBER,
        local_only=True,
        category="argon2",
        description="Argon2 salt length in bytes",
        default=16,
    ),
    _def(
        "auth.argon2.encoding",
        env_var="ARGON2_ENCODING",
        local_only=True,
        category="argon2",
        description="Argon2 string encoding",
        default="utf-8",
    ),
)

# ---------------------------------------------------------------------------
# MITRE ATT&CK  (local_only — loaded once, cached forever)
# ---------------------------------------------------------------------------
_register(
    _def(
        "mitre.attack_stix_path",
        env_var="MITRE_ATTACK_STIX_PATH",
        local_only=True,
        category="mitre",
        description="Path to MITRE ATT&CK STIX bundle JSON file",
        default=None,
    ),
)

# ---------------------------------------------------------------------------
# OIDC  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "oidc.enabled",
        env_var="OIDC_ENABLED",
        value_type=SettingType.BOOLEAN,
        category="oidc",
        description="Enable OpenID Connect single sign-on",
        default=False,
    ),
    _def(
        "oidc.discovery_url",
        env_var="OIDC_DISCOVERY_URL",
        category="oidc",
        description="OpenID Connect discovery URL",
        default=None,
    ),
    _def(
        "oidc.client_id",
        env_var="OIDC_CLIENT_ID",
        category="oidc",
        description="OIDC client ID",
        default=None,
    ),
    _def(
        "oidc.client_secret",
        env_var="OIDC_CLIENT_SECRET",
        is_secret=True,
        category="oidc",
        description="OIDC client secret",
        default=None,
    ),
    _def(
        "oidc.scopes",
        env_var="OIDC_SCOPES",
        category="oidc",
        description="Space-delimited OIDC scopes requested during login",
        default="openid email profile",
    ),
    _def(
        "oidc.provider_name",
        env_var="OIDC_PROVIDER_NAME",
        category="oidc",
        description="Display name for the OIDC provider on the login page",
        default="SSO",
    ),
    _def(
        "oidc.jit_provisioning",
        env_var="OIDC_JIT_PROVISIONING",
        value_type=SettingType.BOOLEAN,
        category="oidc",
        description="Automatically create local user accounts for first-time OIDC sign-ins",
        default=True,
    ),
    _def(
        "oidc.default_role",
        env_var="OIDC_DEFAULT_ROLE",
        category="oidc",
        description="Fallback local role assigned to OIDC users when claim mapping does not apply",
        default="ANALYST",
    ),
    _def(
        "oidc.role_claim_path",
        env_var="OIDC_ROLE_CLAIM_PATH",
        category="oidc",
        description="Dot-path to the OIDC claim used for role mapping, e.g. realm_access.roles",
        default="",
    ),
    _def(
        "oidc.role_mapping",
        env_var="OIDC_ROLE_MAPPING",
        value_type=SettingType.JSON,
        category="oidc",
        description="JSON object mapping IdP claim values to local roles",
        default={},
    ),
    _def(
        "oidc.sso_bypass_users",
        env_var="OIDC_SSO_BYPASS_USERS",
        value_type=SettingType.JSON,
        category="oidc",
        description="JSON array of usernames allowed to use local password login while OIDC is enabled",
        default=[],
    ),
)

# ---------------------------------------------------------------------------
# SMTP  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "smtp.host",
        env_var="SMTP_HOST",
        category="smtp",
        description="SMTP server hostname",
        default="localhost",
    ),
    _def(
        "smtp.port",
        env_var="SMTP_PORT",
        value_type=SettingType.NUMBER,
        category="smtp",
        description="SMTP server port",
        default=1025,
    ),
    _def(
        "smtp.username",
        env_var="SMTP_USERNAME",
        category="smtp",
        description="SMTP authentication username",
        default=None,
    ),
    _def(
        "smtp.password",
        env_var="SMTP_PASSWORD",
        is_secret=True,
        category="smtp",
        description="SMTP authentication password",
        default=None,
    ),
    _def(
        "smtp.use_tls",
        env_var="SMTP_USE_TLS",
        value_type=SettingType.BOOLEAN,
        category="smtp",
        description="Whether to use STARTTLS for SMTP",
        default=False,
    ),
    _def(
        "smtp.from_address",
        env_var="SMTP_FROM_ADDRESS",
        category="smtp",
        description="Sender email address for outgoing mail",
        default="security-admin@example.com",
    ),
)

# ---------------------------------------------------------------------------
# Login protection  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "auth.login.lockout_threshold",
        env_var="LOGIN_LOCKOUT_THRESHOLD",
        value_type=SettingType.NUMBER,
        category="login",
        description="Failed login attempts before account lockout",
        default=5,
    ),
    _def(
        "auth.login.lockout_duration_minutes",
        env_var="LOGIN_LOCKOUT_DURATION_MINUTES",
        value_type=SettingType.NUMBER,
        category="login",
        description="Account lockout duration in minutes",
        default=15,
    ),
    _def(
        "auth.login.rate_limit_attempts",
        env_var="LOGIN_RATE_LIMIT_ATTEMPTS",
        value_type=SettingType.NUMBER,
        category="login",
        description="Max login attempts per rate-limit window",
        default=10,
    ),
    _def(
        "auth.login.rate_limit_window_seconds",
        env_var="LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        value_type=SettingType.NUMBER,
        category="login",
        description="Rate-limit sliding window in seconds",
        default=60,
    ),
)

# ---------------------------------------------------------------------------
# LangFlow AI integration  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "langflow.base_url",
        category="langflow",
        description="LangFlow API base URL",
        default=None,
    ),
    _def(
        "langflow.api_key",
        is_secret=True,
        category="langflow",
        description="LangFlow API key",
        default=None,
    ),
    _def(
        "langflow.timeout",
        value_type=SettingType.NUMBER,
        category="langflow",
        description="LangFlow HTTP request timeout in seconds",
        default=30,
    ),
    _def(
        "langflow.default_flow_id",
        category="langflow",
        description="Default LangFlow flow ID for general chat",
        default=None,
    ),
    _def(
        "langflow.case_detail_flow_id",
        category="langflow",
        description="LangFlow flow ID for case context chat",
        default=None,
    ),
    _def(
        "langflow.task_detail_flow_id",
        category="langflow",
        description="LangFlow flow ID for task context chat",
        default=None,
    ),
    _def(
        "langflow.alert_triage_flow_id",
        category="langflow",
        description="LangFlow flow ID for alert triage",
        default=None,
    ),
)

# ---------------------------------------------------------------------------
# Feature flags / triage  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "triage.auto_enqueue",
        value_type=SettingType.BOOLEAN,
        category="features",
        description="Automatically enqueue new alerts for AI triage",
        default=False,
    ),
    _def(
        "case_closure.recommended_tags",
        value_type=SettingType.JSON,
        category="features",
        description="Recommended tags for case closure",
        default=None,
    ),
)

# ---------------------------------------------------------------------------
# Passkey / WebAuthn  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "auth.passkeys.rp_id",
        category="passkeys",
        description="WebAuthn Relying Party ID (usually the domain)",
        default="localhost",
    ),
    _def(
        "auth.passkeys.rp_name",
        category="passkeys",
        description="WebAuthn Relying Party display name",
        default="Tidemark Intercept",
    ),
    _def(
        "auth.passkeys.expected_origins",
        value_type=SettingType.JSON,
        category="passkeys",
        description="Allowed WebAuthn origins (JSON array or comma-separated string)",
        default=None,
    ),
    _def(
        "auth.passkeys.timeout_ms",
        value_type=SettingType.NUMBER,
        category="passkeys",
        description="WebAuthn challenge timeout in milliseconds",
        default=60000,
    ),
    _def(
        "auth.passkeys.challenge_ttl_seconds",
        value_type=SettingType.NUMBER,
        category="passkeys",
        description="WebAuthn challenge time-to-live in seconds",
        default=300,
    ),
    _def(
        "auth.passkeys.user_verification",
        category="passkeys",
        description="WebAuthn user verification requirement (required, preferred, discouraged)",
        default="required",
    ),
    _def(
        "auth.passkeys.resident_key",
        category="passkeys",
        description="WebAuthn resident key requirement (required, preferred, discouraged)",
        default="preferred",
    ),
    _def(
        "auth.passkeys.attestation",
        category="passkeys",
        description="WebAuthn attestation conveyance (none, indirect, direct, enterprise)",
        default="none",
    ),
    _def(
        "auth.passkeys.authenticator_attachment",
        category="passkeys",
        description="WebAuthn authenticator attachment (platform, cross-platform, or null for any)",
        default=None,
    ),
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()

# Lazy-loaded .env mapping – populated once on first call to ``get_local``.
_dotenv_values: Optional[Dict[str, str]] = None


def _load_dotenv() -> Dict[str, str]:
    """Load ``.env`` file once and cache the result."""
    global _dotenv_values
    if _dotenv_values is None:
        try:
            from dotenv import dotenv_values  # shipped with pydantic-settings
            _dotenv_values = {k: v for k, v in dotenv_values(".env").items() if v is not None}
        except ImportError:
            _dotenv_values = {}
    return _dotenv_values


def get_local(key: str, default: Any = _SENTINEL) -> Any:
    """Read a setting value from environment / .env only (no database).

    Intended for bootstrap-phase and singleton callers that cannot use
    the async ``SettingsService``.

    Resolution order:
        1. ``os.environ[env_var]``  (real environment variable)
        2. ``.env`` file value (loaded via python-dotenv)
        3. Registry default
        4. *default* argument (if provided)

    Raises ``KeyError`` if the key is not in the registry and no *default*
    is supplied.
    """
    import os

    defn = SETTINGS_REGISTRY.get(key)
    if defn is None:
        if default is _SENTINEL:
            raise KeyError(f"Unknown setting key: {key!r}")
        return default

    # 1. Real environment variable
    raw = os.getenv(defn.env_var)
    if raw is not None:
        return _coerce(raw, defn.value_type)

    # 2. .env file
    dotenv = _load_dotenv()
    raw = dotenv.get(defn.env_var)
    if raw is not None:
        return _coerce(raw, defn.value_type)

    # 3. Registry default
    if defn.default is not None:
        return defn.default

    # 4. Caller-supplied default
    if default is not _SENTINEL:
        return default

    return defn.default  # may be None


def _coerce(raw: str, value_type: SettingType) -> Any:
    """Coerce a raw string value based on SettingType."""
    import json

    if value_type == SettingType.NUMBER:
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    elif value_type == SettingType.BOOLEAN:
        return raw.lower() in ("true", "1", "yes", "on")
    elif value_type == SettingType.JSON:
        return json.loads(raw)
    return raw
