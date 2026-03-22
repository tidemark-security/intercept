"""LDAP/Active Directory user enrichment provider.

Uses the ldap3 library for LDAP queries.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import AliasMapping, EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

_DEFAULT_ATTRIBUTES = [
    "objectGUID",
    "distinguishedName",
    "cn",
    "displayName",
    "givenName",
    "sn",
    "mail",
    "userPrincipalName",
    "sAMAccountName",
    "employeeID",
    "title",
    "department",
    "company",
    "physicalDeliveryOfficeName",
    "telephoneNumber",
    "mobile",
    "manager",
    "memberOf",
]

_USER_SEARCH_FILTER_TEMPLATE = (
    "(|"
    "(sAMAccountName={uid})"
    "(userPrincipalName={uid})"
    "(mail={uid})"
    "(cn={uid})"
    "(displayName={uid})"
    ")"
)

_BULK_SYNC_FILTER = "(&(objectClass=user)(objectCategory=person))"


def _format_object_guid(raw: Any) -> str:
    """Format raw objectGUID bytes into a standard GUID string."""
    if isinstance(raw, bytes) and len(raw) == 16:
        b = raw
        return (
            f"{b[3]:02x}{b[2]:02x}{b[1]:02x}{b[0]:02x}-"
            f"{b[5]:02x}{b[4]:02x}-"
            f"{b[7]:02x}{b[6]:02x}-"
            f"{b[8]:02x}{b[9]:02x}-"
            f"{b[10]:02x}{b[11]:02x}{b[12]:02x}{b[13]:02x}{b[14]:02x}{b[15]:02x}"
        )
    if isinstance(raw, str):
        return raw
    return str(raw)


class LDAPProvider(EnrichmentProvider):
    """Enrich InternalActorItem via LDAP/Active Directory."""

    provider_id = "ldap"
    display_name = "LDAP / Active Directory"
    settings_prefix = "enrichment.ldap"
    supported_item_types = ("internal_actor",)
    supports_bulk_sync = True

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor" and bool(self._get_identifier(item))

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for LDAP cache key")
        return f"user:{identifier}"

    def _get_identifier(self, item: Dict[str, Any]) -> str:
        for key in ("user_id", "contact_email", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        url = await settings.get(f"{self.settings_prefix}.url", "")
        bind_dn = await settings.get(f"{self.settings_prefix}.bind_dn", "")
        bind_password = await settings.get(f"{self.settings_prefix}.bind_password", "")
        search_base = await settings.get(f"{self.settings_prefix}.search_base", "")
        use_ssl = await settings.get(f"{self.settings_prefix}.use_ssl", True)
        user_search_filter = await settings.get(
            f"{self.settings_prefix}.user_search_filter",
            _USER_SEARCH_FILTER_TEMPLATE,
        )
        if not (url and bind_dn and bind_password and search_base):
            return None
        return {
            "url": url,
            "bind_dn": bind_dn,
            "bind_password": bind_password,
            "search_base": search_base,
            "use_ssl": bool(use_ssl),
            "user_search_filter": user_search_filter,
        }

    def _connect(self, url: str, bind_dn: str, bind_password: str, use_ssl: bool) -> Any:
        """Create and bind an ldap3 Connection. Raises ImportError if ldap3 not installed."""
        try:
            import ldap3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "ldap3 is required for the LDAP enrichment provider. "
                "Install it with: pip install ldap3"
            ) from exc

        server = ldap3.Server(url, get_info=ldap3.NONE, connect_timeout=10, use_ssl=use_ssl)
        conn = ldap3.Connection(
            server,
            user=bind_dn,
            password=bind_password,
            authentication=ldap3.SIMPLE,
            auto_bind=True,
            read_only=True,
        )
        return conn

    def _entry_to_str(self, entry: Any, attr: str) -> str:
        """Safely extract a string attribute from an ldap3 entry."""
        val = getattr(entry, attr, None)
        if val is None:
            return ""
        raw = val.value if hasattr(val, "value") else val
        if isinstance(raw, list):
            return str(raw[0]) if raw else ""
        if raw is None:
            return ""
        return str(raw)

    def _build_result(self, entry: Any, *, cache_key: str) -> EnrichmentResult:
        def _s(attr: str) -> str:
            return self._entry_to_str(entry, attr)

        guid_raw = getattr(entry, "objectGUID", None)
        if guid_raw is not None:
            guid_raw = guid_raw.value if hasattr(guid_raw, "value") else guid_raw
        object_guid = _format_object_guid(guid_raw) if guid_raw else ""

        display_name = _s("displayName") or _s("cn")
        email = _s("mail")
        upn = _s("userPrincipalName")
        sam = _s("sAMAccountName")
        manager_dn = _s("manager")
        manager_cn = manager_dn.split(",")[0].removeprefix("CN=") if manager_dn else ""

        enrichment_data = {
            "object_guid": object_guid,
            "distinguished_name": _s("distinguishedName"),
            "display_name": display_name,
            "given_name": _s("givenName"),
            "surname": _s("sn"),
            "email": email,
            "upn": upn,
            "sam_account_name": sam,
            "employee_id": _s("employeeID"),
            "job_title": _s("title"),
            "department": _s("department"),
            "company": _s("company"),
            "office": _s("physicalDeliveryOfficeName"),
            "phone": _s("telephoneNumber"),
            "mobile": _s("mobile"),
            "manager_dn": manager_dn,
            "manager_cn": manager_cn,
        }

        canonical_id = upn.lower() or sam.lower() or email.lower() or object_guid or cache_key
        canonical_display = display_name or email or canonical_id
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
                        canonical_value=canonical_id,
                        canonical_display=canonical_display,
                        alias_type=alias_type,
                        alias_value=value,
                        attributes=meta,
                    )
                )

        if object_guid:
            _add("object_guid", object_guid)
        _add("samaccountname", sam.lower() if sam else "")
        _add("email", email.lower() if email else "")
        _add("upn", upn.lower() if upn else "")
        _add("display_name", display_name.lower() if display_name else "")
        if _s("employeeID"):
            _add("employee_id", _s("employeeID"))

        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=cache_key,
            enrichment_data=enrichment_data,
            aliases=aliases,
        )

    def _escape_identifier(self, value: str) -> str:
        from ldap3.utils.conv import escape_filter_chars  # type: ignore[import-untyped]

        return escape_filter_chars(value)

    def _build_user_search_filter(self, template: str, identifier: str) -> str:
        escaped_identifier = self._escape_identifier(identifier)
        return template.replace("{value}", escaped_identifier).format(uid=escaped_identifier)

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
            raise ValueError("LDAP provider is not fully configured")

        identifier = self._get_identifier(item)
        if not identifier:
            raise ValueError("Cannot determine identifier for LDAP lookup")

        result = await asyncio.to_thread(self._sync_lookup, cfg, identifier, self.build_cache_key(item))
        return result

    def _sync_lookup(self, cfg: Dict[str, Any], identifier: str, cache_key: str) -> EnrichmentResult:
        conn = self._connect(cfg["url"], cfg["bind_dn"], cfg["bind_password"], cfg["use_ssl"])
        try:
            search_filter = self._build_user_search_filter(cfg["user_search_filter"], identifier)
            conn.search(
                cfg["search_base"],
                search_filter,
                attributes=_DEFAULT_ATTRIBUTES,
            )
            if not conn.entries:
                return EnrichmentResult(
                    provider_id=self.provider_id,
                    cache_key=cache_key,
                    enrichment_data={"error": f"User not found: {identifier}"},
                )
            return self._build_result(conn.entries[0], cache_key=cache_key)
        finally:
            conn.unbind()

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        cfg = await self._get_settings(settings)
        if not cfg:
            raise ValueError("LDAP provider is not fully configured")

        results = await asyncio.to_thread(self._sync_bulk_search, cfg)
        logger.info("LDAP bulk sync: %d users", len(results))
        return results

    def _sync_bulk_search(self, cfg: Dict[str, Any]) -> List[EnrichmentResult]:
        conn = self._connect(cfg["url"], cfg["bind_dn"], cfg["bind_password"], cfg["use_ssl"])
        try:
            results: List[EnrichmentResult] = []
            conn.search(
                cfg["search_base"],
                _BULK_SYNC_FILTER,
                attributes=_DEFAULT_ATTRIBUTES,
                paged_size=500,
            )
            while True:
                for entry in conn.entries:
                    try:
                        canonical = (
                            self._entry_to_str(entry, "userPrincipalName")
                            or self._entry_to_str(entry, "mail")
                            or self._entry_to_str(entry, "sAMAccountName")
                            or _format_object_guid(getattr(getattr(entry, "objectGUID", None), "value", None))
                        )
                        if not canonical:
                            continue
                        results.append(self._build_result(entry, cache_key=f"user:{canonical.strip().lower()}"))
                    except Exception as exc:
                        logger.warning("LDAP: skipping entry %s: %s", getattr(entry, "distinguishedName", "?"), exc)

                # Handle paged results
                cookie = conn.result.get("controls", {}).get("1.2.840.113556.1.4.319", {}).get("value", {}).get("cookie")
                if not cookie:
                    break
                conn.search(
                    cfg["search_base"],
                    _BULK_SYNC_FILTER,
                    attributes=_DEFAULT_ATTRIBUTES,
                    paged_size=500,
                    paged_cookie=cookie,
                )
            return results
        finally:
            conn.unbind()


ldap_provider = LDAPProvider()
