"""Google Workspace user enrichment provider.

Uses the Google Admin SDK Directory API with a service account JWT.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_ADMIN_SDK_BASE = "https://admin.googleapis.com/admin/directory/v1"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
_USER_FIELDS = "id,primaryEmail,name,givenName,familyName,emails,phones,organizations,aliases,thumbnailPhotoUrl,suspended"


def _build_jwt(service_account: Dict[str, Any], subject_email: str) -> str:
    """Build a signed JWT for service account authentication."""
    try:
        import base64
        import hashlib
        import hmac

        # Use cryptography / jwt library if available, else fall back to manual
        try:
            import jwt  # type: ignore[import-untyped]
            import cryptography  # noqa: F401
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            private_key = load_pem_private_key(service_account["private_key"].encode(), password=None)
            now = int(time.time())
            payload = {
                "iss": service_account["client_email"],
                "sub": subject_email,
                "scope": _SCOPE,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }
            return jwt.encode(payload, private_key, algorithm="RS256")
        except ImportError:
            pass

        # Fallback: manual RS256 JWT via stdlib (requires openssl available via subprocess)
        import base64 as _b64
        import json as _json
        import subprocess

        header = _b64.urlsafe_b64encode(_json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        now = int(time.time())
        claim = _b64.urlsafe_b64encode(
            _json.dumps({
                "iss": service_account["client_email"],
                "sub": subject_email,
                "scope": _SCOPE,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }).encode()
        ).rstrip(b"=").decode()
        signing_input = f"{header}.{claim}".encode()
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", "/dev/stdin"],
            input=service_account["private_key"].encode(),
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"openssl failed: {result.stderr.decode()}")
        sig = _b64.urlsafe_b64encode(result.stdout).rstrip(b"=").decode()
        return f"{header}.{claim}.{sig}"
    except Exception as exc:
        raise RuntimeError(f"Cannot build service account JWT: {exc}") from exc


class GoogleWorkspaceProvider(EnrichmentProvider):
    """Enrich InternalActorItem via Google Workspace Admin SDK."""

    provider_id = "google_workspace"
    display_name = "Google Workspace"
    settings_prefix = "enrichment.google_workspace"
    supported_item_types = ("internal_actor",)
    supports_bulk_sync = True

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor"

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        actor = item.get("actor") or {}
        return (actor.get("user_id") or actor.get("email") or actor.get("name") or "").strip().lower()

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        sa_json = await settings.get(f"{self.settings_prefix}.service_account_json", "")
        domain = await settings.get(f"{self.settings_prefix}.domain", "")
        admin_email = await settings.get(f"{self.settings_prefix}.admin_email", "")
        if not sa_json:
            return None
        try:
            sa = json.loads(sa_json)
        except json.JSONDecodeError:
            return None
        return {"service_account": sa, "domain": domain, "admin_email": admin_email}

    async def _get_token(self, service_account: Dict[str, Any], admin_email: str) -> str:
        jwt_token = _build_jwt(service_account, admin_email)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt_token,
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    def _build_result(self, user: Dict[str, Any]) -> EnrichmentResult:
        google_id = user.get("id", "")
        primary_email = user.get("primaryEmail", "")
        name = user.get("name") or {}
        display_name = name.get("fullName") or ""
        given_name = name.get("givenName") or ""
        family_name = name.get("familyName") or ""

        org_info = (user.get("organizations") or [{}])[0]
        phone_info = (user.get("phones") or [{}])[0]

        enrichment_data = {
            "google_id": google_id,
            "primary_email": primary_email,
            "display_name": display_name,
            "given_name": given_name,
            "family_name": family_name,
            "job_title": org_info.get("title") or "",
            "department": org_info.get("department") or "",
            "organization": org_info.get("name") or "",
            "phone": phone_info.get("value") or "",
            "suspended": user.get("suspended", False),
        }

        canonical_display = display_name or primary_email or google_id
        meta = {
            "department": enrichment_data["department"],
            "job_title": enrichment_data["job_title"],
            "display_name": display_name,
        }

        aliases: List[AliasMapping] = []

        def _add(alias_type: str, value: str) -> None:
            if value:
                aliases.append(
                    AliasMapping(
                        entity_type="user",
                        canonical_value=google_id,
                        canonical_display=canonical_display,
                        alias_type=alias_type,
                        alias_value=value,
                        attributes=meta,
                    )
                )

        _add("google_id", google_id)
        _add("email", primary_email.lower() if primary_email else "")
        _add("display_name", display_name.lower() if display_name else "")

        for alt in user.get("emails") or []:
            alt_addr = alt.get("address") or ""
            if alt_addr and alt_addr.lower() != primary_email.lower():
                _add("email", alt_addr.lower())

        for alias_email in user.get("aliases") or []:
            _add("email_alias", alias_email.lower())

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=google_id or primary_email,
            enrichment_data=enrichment_data,
            aliases=aliases,
        )

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise ValueError("Google Workspace provider is not fully configured")

        actor = item.get("actor") or {}
        identifier = (actor.get("user_id") or actor.get("email") or actor.get("name") or "").strip()
        if not identifier:
            raise ValueError("Cannot determine identifier for Google Workspace lookup")

        token = await self._get_token(cfg["service_account"], cfg["admin_email"])
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_ADMIN_SDK_BASE}/users/{identifier}",
                headers=headers,
                params={"fields": _USER_FIELDS, "viewType": "admin_view"},
            )
            if resp.status_code == 404:
                return EnrichmentResult(
                    provider_id=self.provider_id,
                    cache_key=identifier,
                    enrichment_data={"error": f"User not found: {identifier}"},
                )
            resp.raise_for_status()
            user = resp.json()

        return self._build_result(user)

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise ValueError("Google Workspace provider is not fully configured")

        token = await self._get_token(cfg["service_account"], cfg["admin_email"])
        headers = {"Authorization": f"Bearer {token}"}
        domain = cfg.get("domain") or ""
        results: List[EnrichmentResult] = []
        page_token: Optional[str] = None

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params: Dict[str, Any] = {
                    "fields": f"nextPageToken,users({_USER_FIELDS})",
                    "maxResults": 500,
                    "orderBy": "email",
                }
                if domain:
                    params["domain"] = domain
                else:
                    params["customer"] = "my_customer"
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(f"{_ADMIN_SDK_BASE}/users", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                for user in data.get("users") or []:
                    try:
                        results.append(self._build_result(user))
                    except Exception as exc:
                        logger.warning("Google Workspace: skipping user %s: %s", user.get("id"), exc)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        logger.info("Google Workspace bulk sync: %d users", len(results))
        return results


google_workspace_provider = GoogleWorkspaceProvider()
