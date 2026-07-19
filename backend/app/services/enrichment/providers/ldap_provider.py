"""LDAP/Active Directory user enrichment provider.

Uses the ldap3 library for LDAP queries.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.base import (
    EnrichmentProviderConfigurationError,
    EnrichmentProviderError,
    EnrichmentResult,
    MalformedProviderRecordError,
    UserDirectoryEnrichmentProvider,
)
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

_BULK_SYNC_FILTER = "(&(objectClass=user)(objectCategory=person))"


def _format_object_guid(raw: Any) -> str:
    """Format raw objectGUID bytes into a standard GUID string."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        if len(raw) != 16:
            raise MalformedProviderRecordError(
                "LDAP objectGUID must contain exactly 16 bytes"
            )
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
    raise MalformedProviderRecordError(
        "LDAP objectGUID must be a string or 16-byte value"
    )


class LDAPProvider(UserDirectoryEnrichmentProvider):
    """Enrich InternalActorItem via LDAP/Active Directory."""

    provider_id = "ldap"
    display_name = "LDAP / Active Directory"
    settings_prefix = "enrichment.ldap"
    supports_bulk_sync = True

    async def _get_settings(self, settings: SettingsService) -> Optional[Dict[str, Any]]:
        values = await self._get_setting_values(
            settings,
            (
                "url",
                "bind_dn",
                "bind_password",
                "search_base",
                "use_ssl",
                "ca_certs_file",
                "user_search_filter",
            ),
        )
        url = values["url"]
        bind_dn = values["bind_dn"]
        bind_password = values["bind_password"]
        search_base = values["search_base"]
        if not (url and bind_dn and bind_password and search_base):
            return None
        return {
            "url": url,
            "bind_dn": bind_dn,
            "bind_password": bind_password,
            "search_base": search_base,
            "use_ssl": bool(values["use_ssl"]),
            "ca_certs_file": str(values["ca_certs_file"]).strip() if values["ca_certs_file"] else None,
            "user_search_filter": values["user_search_filter"],
        }

    def _connect(
        self,
        url: str,
        bind_dn: str,
        bind_password: str,
        use_ssl: bool,
        ca_certs_file: Optional[str] = None,
    ) -> Any:
        """Create and bind an ldap3 Connection. Raises ImportError if ldap3 not installed."""
        try:
            import ldap3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "ldap3 is required for the LDAP enrichment provider. "
                "Install it with: pip install ldap3"
            ) from exc

        tls = None
        if use_ssl:
            tls = ldap3.Tls(
                ca_certs_file=ca_certs_file,
                validate=ssl.CERT_REQUIRED,
                version=ssl.PROTOCOL_TLS_CLIENT,
            )

        server = ldap3.Server(
            url,
            get_info=ldap3.NONE,
            connect_timeout=10,
            use_ssl=use_ssl,
            tls=tls,
        )
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

        alias_values = []
        if object_guid:
            alias_values.append(("object_guid", object_guid))
        alias_values.extend(
            [
                ("samaccountname", sam.lower() if sam else ""),
                ("email", email.lower() if email else ""),
                ("upn", upn.lower() if upn else ""),
                ("display_name", display_name.lower() if display_name else ""),
            ]
        )
        if _s("employeeID"):
            alias_values.append(("employee_id", _s("employeeID")))

        aliases = self._build_alias_mappings(
            entity_type="user",
            canonical_value=canonical_id,
            canonical_display=canonical_display,
            attributes=meta,
            aliases=alias_values,
        )

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
        return template.replace("{uid}", escaped_identifier).replace("{value}", escaped_identifier)

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
            raise EnrichmentProviderConfigurationError(
                "LDAP provider is not fully configured"
            )

        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                "Cannot determine identifier for LDAP lookup"
            )

        result = await asyncio.to_thread(self._sync_lookup, cfg, identifier, self.build_cache_key(item))
        return result

    def _sync_lookup(self, cfg: Dict[str, Any], identifier: str, cache_key: str) -> EnrichmentResult:
        conn = self._connect_with_config(cfg)
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
            raise EnrichmentProviderConfigurationError(
                "LDAP provider is not fully configured"
            )

        results = await asyncio.to_thread(self._sync_bulk_search, cfg)
        logger.info("LDAP bulk sync: %d users", len(results))
        return results

    def _sync_bulk_search(self, cfg: Dict[str, Any]) -> List[EnrichmentResult]:
        conn = self._connect_with_config(cfg)
        try:
            results: List[EnrichmentResult] = []
            malformed_records = 0
            conn.search(
                cfg["search_base"],
                _BULK_SYNC_FILTER,
                attributes=_DEFAULT_ATTRIBUTES,
                paged_size=500,
            )
            while True:
                for entry in conn.entries:
                    try:
                        cache_key = self._build_user_cache_key_from_values(
                            self._entry_to_str(entry, "userPrincipalName"),
                            self._entry_to_str(entry, "mail"),
                            self._entry_to_str(entry, "sAMAccountName"),
                            _format_object_guid(
                                getattr(
                                    getattr(entry, "objectGUID", None),
                                    "value",
                                    None,
                                )
                            ),
                        )
                        results.append(
                            self._build_result(entry, cache_key=cache_key)
                        )
                    except MalformedProviderRecordError:
                        malformed_records += 1

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
            if malformed_records:
                logger.warning(
                    "LDAP bulk sync skipped malformed user records (count=%d)",
                    malformed_records,
                )
            return results
        finally:
            conn.unbind()

    def _connect_with_config(self, cfg: Dict[str, Any]) -> Any:
        ca_certs_file = cfg.get("ca_certs_file")
        if ca_certs_file:
            return self._connect(
                cfg["url"],
                cfg["bind_dn"],
                cfg["bind_password"],
                cfg["use_ssl"],
                ca_certs_file,
            )
        return self._connect(
            cfg["url"],
            cfg["bind_dn"],
            cfg["bind_password"],
            cfg["use_ssl"],
        )


ldap_provider = LDAPProvider()
