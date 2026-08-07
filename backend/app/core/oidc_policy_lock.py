"""Transaction-scoped ordering gate for main-application OIDC policy."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Keep this namespace separate from account authorization and the bounded OIDC
# request ledger.  The lock is transaction-scoped so an enablement writer can
# linearize policy commits against callbacks that are about to resolve an identity
# and issue an application session.
_OIDC_POLICY_LOCK_ID = 0x544D_4F49_4450

# Every hot-swappable DB setting that can change identity validation,
# provisioning, authorization, local-credential posture, or the post-login
# redirect is one policy domain. ``oidc.provider_name`` is intentionally absent:
# it is display text only. The remaining omitted OIDC settings are local-only
# process configuration and therefore cannot be mutated through SettingsService.
OIDC_AUTHORIZATION_POLICY_SETTING_KEYS = frozenset(
    {
        "oidc.enabled",
        "oidc.discovery_url",
        "oidc.client_id",
        "oidc.client_secret",
        "oidc.scopes",
        "oidc.jit_provisioning",
        "oidc.default_role",
        "oidc.role_claim_path",
        "oidc.role_mapping",
        "oidc.sso_bypass_users",
        "oidc.allowed_redirect_origins",
    }
)


def oidc_setting_requires_policy_gate(key: str) -> bool:
    """Return whether a DB setting participates in OIDC authorization policy."""

    return key in OIDC_AUTHORIZATION_POLICY_SETTING_KEYS


async def acquire_oidc_policy_lock(
    db: AsyncSession,
    *,
    shared: bool,
) -> None:
    """Acquire the main-app OIDC policy gate for the current transaction."""

    function_name = (
        "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    )
    await db.execute(
        text(f"SELECT {function_name}(:lock_key)"),  # noqa: S608 - fixed names above
        {"lock_key": _OIDC_POLICY_LOCK_ID},
    )


__all__ = [
    "OIDC_AUTHORIZATION_POLICY_SETTING_KEYS",
    "acquire_oidc_policy_lock",
    "oidc_setting_requires_policy_gate",
]
