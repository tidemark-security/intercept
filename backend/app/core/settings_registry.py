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


def _bulk_sync_schedule_defs(provider_id: str, provider_label: str) -> tuple[SettingDefinition, SettingDefinition]:
    return (
        _def(
            f"enrichment.{provider_id}.bulk_sync_enabled",
            value_type=SettingType.BOOLEAN,
            category="enrichment",
            description=f"Enable daily pgqueuer-backed bulk sync scheduling for {provider_label}",
            default=False,
        ),
        _def(
            f"enrichment.{provider_id}.bulk_sync_time_utc",
            category="enrichment",
            description=f"Daily UTC time for {provider_label} bulk sync in HH:MM format",
            default="",
        ),
    )


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
    _def(
        "auth.csrf.enabled",
        env_var="CSRF_ENABLED",
        value_type=SettingType.BOOLEAN,
        local_only=True,
        category="session",
        description="Whether CSRF validation is enforced for session-cookie mutations",
        default=True,
    ),
    _def(
        "auth.csrf.cookie_name",
        env_var="CSRF_COOKIE_NAME",
        local_only=True,
        category="session",
        description="Name of the readable CSRF cookie",
        default="XSRF-TOKEN",
    ),
    _def(
        "auth.csrf.header_name",
        env_var="CSRF_HEADER_NAME",
        local_only=True,
        category="session",
        description="Header that must mirror the CSRF cookie on unsafe requests",
        default="X-XSRF-TOKEN",
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
# Reset token  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "reset_token.expiry_minutes",
        env_var="RESET_TOKEN_EXPIRY_MINUTES",
        value_type=SettingType.NUMBER,
        category="security",
        description="Minutes before an admin-issued password reset token expires",
        default=30,
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
    _def(
        "oidc.allowed_redirect_origins",
        env_var="OIDC_ALLOWED_REDIRECT_ORIGINS",
        value_type=SettingType.JSON,
        category="oidc",
        description="JSON array of allowed frontend origins for the OIDC next parameter",
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
    ),
    _def(
        "oidc.browser_binding.cookie_name",
        env_var="OIDC_BROWSER_BINDING_COOKIE_NAME",
        local_only=True,
        category="oidc",
        description="Cookie used to bind an OIDC login flow to the initiating browser",
        default="intercept_oidc_binding",
    ),
)

# ---------------------------------------------------------------------------
# Attachment storage and preview limits  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "storage.max_upload_size_mb",
        env_var="MAX_UPLOAD_SIZE_MB",
        value_type=SettingType.NUMBER,
        category="storage",
        description="Maximum attachment upload size in megabytes",
        default=50,
    ),
    _def(
        "storage.max_image_preview_size_mb",
        value_type=SettingType.NUMBER,
        category="storage",
        description="Maximum image attachment size in megabytes that will render an inline preview",
        default=5,
    ),
    _def(
        "storage.max_text_preview_size_mb",
        value_type=SettingType.NUMBER,
        category="storage",
        description="Maximum text attachment size in megabytes that will render an inline preview",
        default=1,
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
# Enrichment framework  (hot-swappable)
# ---------------------------------------------------------------------------
_register(
    _def(
        "enrichment.cache.default_ttl_seconds",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="Default TTL for provider cache entries in seconds",
        default=86400,
    ),
    _def(
        "enrichment.cache.hot_cache_max_size",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="Maximum number of process-local enrichment cache entries",
        default=1024,
    ),
    _def(
        "enrichment.entra_id.enabled",
        value_type=SettingType.BOOLEAN,
        category="enrichment",
        description="Enable Microsoft Entra ID user enrichment provider",
        default=False,
    ),
    _def(
        "enrichment.entra_id.tenant_id",
        category="enrichment",
        description="Microsoft Entra tenant ID used for Graph API authentication",
        default=None,
    ),
    _def(
        "enrichment.entra_id.client_id",
        category="enrichment",
        description="Microsoft Entra client ID for the enrichment application",
        default=None,
    ),
    _def(
        "enrichment.entra_id.client_secret",
        is_secret=True,
        category="enrichment",
        description="Microsoft Entra client secret for the enrichment application",
        default=None,
    ),
    _def(
        "enrichment.entra_id.ttl_seconds",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="TTL for Microsoft Entra enrichment results in seconds",
        default=86400,
    ),
    _def(
        "enrichment.google_workspace.enabled",
        value_type=SettingType.BOOLEAN,
        category="enrichment",
        description="Enable Google Workspace user enrichment provider",
        default=False,
    ),
    _def(
        "enrichment.google_workspace.domain",
        category="enrichment",
        description="Primary Google Workspace domain for directory lookups",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.client_email",
        category="enrichment",
        description="Google service account client email used for directory access",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.private_key",
        is_secret=True,
        category="enrichment",
        description="Google service account private key used for directory access",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.private_key_id",
        category="enrichment",
        description="Optional Google service account private key ID",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.token_uri",
        category="enrichment",
        description="Token URI used for Google service account access token exchange",
        default="https://oauth2.googleapis.com/token",
    ),
    _def(
        "enrichment.google_workspace.service_account_json",
        is_secret=True,
        category="enrichment",
        description="Deprecated legacy Google service account JSON blob used for directory access fallback",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.admin_email",
        category="enrichment",
        description="Admin email to impersonate for Google Workspace directory access",
        default=None,
    ),
    _def(
        "enrichment.google_workspace.ttl_seconds",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="TTL for Google Workspace enrichment results in seconds",
        default=86400,
    ),
    _def(
        "enrichment.ldap.enabled",
        value_type=SettingType.BOOLEAN,
        category="enrichment",
        description="Enable LDAP user enrichment provider",
        default=False,
    ),
    _def(
        "enrichment.ldap.url",
        category="enrichment",
        description="LDAP or LDAPS connection URL",
        default=None,
    ),
    _def(
        "enrichment.ldap.bind_dn",
        category="enrichment",
        description="LDAP bind DN for enrichment queries",
        default=None,
    ),
    _def(
        "enrichment.ldap.bind_password",
        is_secret=True,
        category="enrichment",
        description="LDAP bind password for enrichment queries",
        default=None,
    ),
    _def(
        "enrichment.ldap.search_base",
        category="enrichment",
        description="LDAP base DN used for user searches",
        default=None,
    ),
    _def(
        "enrichment.ldap.use_ssl",
        value_type=SettingType.BOOLEAN,
        category="enrichment",
        description="Use SSL/TLS when connecting to the LDAP server",
        default=True,
    ),
    _def(
        "enrichment.ldap.user_search_filter",
        category="enrichment",
        description="LDAP search filter template for on-demand user lookups; use {uid} as the placeholder",
        default="(|(sAMAccountName={uid})(userPrincipalName={uid})(mail={uid}))",
    ),
    _def(
        "enrichment.ldap.ttl_seconds",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="TTL for LDAP enrichment results in seconds",
        default=86400,
    ),
    _def(
        "enrichment.maxmind.enabled",
        value_type=SettingType.BOOLEAN,
        category="enrichment",
        description="Enable MaxMind MMDB enrichment provider",
        default=False,
    ),
    _def(
        "enrichment.maxmind.account_id",
        category="enrichment",
        description="MaxMind account ID used for direct database downloads",
        default=None,
    ),
    _def(
        "enrichment.maxmind.license_key",
        is_secret=True,
        category="enrichment",
        description="MaxMind license key used for direct database downloads",
        default=None,
    ),
    _def(
        "enrichment.maxmind.edition_ids",
        value_type=SettingType.JSON,
        category="enrichment",
        description="Configured MaxMind MMDB editions to download and use for enrichment",
        default=["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"],
    ),
    _def(
        "enrichment.maxmind.ttl_seconds",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="TTL for MaxMind enrichment results in seconds",
        default=604800,
    ),
    _def(
        "enrichment.maxmind.update_frequency_hours",
        value_type=SettingType.NUMBER,
        category="enrichment",
        description="How often workers should check for MaxMind database updates",
        default=24,
    ),
    _def(
        "enrichment.maxmind.local_cache_dir",
        category="enrichment",
        description="Local filesystem directory where workers cache MaxMind MMDB files",
        default="/tmp/tmi-maxmind",
        local_only=True,
    ),
    _def(
        "enrichment.maxmind.storage_prefix",
        category="enrichment",
        description="Blob storage prefix used for MaxMind MMDB and metadata objects",
        default="maxmind/",
        local_only=True,
    ),
    *_bulk_sync_schedule_defs("entra_id", "Microsoft Entra ID"),
    *_bulk_sync_schedule_defs("google_workspace", "Google Workspace"),
    *_bulk_sync_schedule_defs("ldap", "LDAP / Active Directory"),
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
