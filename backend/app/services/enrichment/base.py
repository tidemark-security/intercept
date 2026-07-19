from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_setting_default
from app.services.settings_service import SettingsService


class EnrichmentProviderError(ValueError):
    """Base class for expected provider rejections and integration responses."""


class EnrichmentProviderConfigurationError(EnrichmentProviderError):
    """Raised when an enrichment provider is absent or misconfigured."""


class MalformedProviderRecordError(EnrichmentProviderError):
    """An external provider record does not match its documented shape."""


@dataclass(slots=True)
class AliasMapping:
    """Canonical alias mapping produced by an enrichment provider."""

    entity_type: str
    canonical_value: str
    canonical_display: str | None = None
    alias_type: str = "alias"
    alias_value: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EnrichmentResult:
    """Provider enrichment result for a single timeline item."""

    provider_id: str
    cache_key: str
    enrichment_data: Dict[str, Any] = field(default_factory=dict)
    aliases: List[AliasMapping] = field(default_factory=list)
    timeline_reply: Dict[str, Any] | None = None
    ttl_seconds: int | None = None

    def to_cache_payload(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "cache_key": self.cache_key,
            "enrichment_data": self.enrichment_data,
            "aliases": [asdict(alias) for alias in self.aliases],
            "timeline_reply": self.timeline_reply,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_cache_payload(cls, payload: Dict[str, Any]) -> "EnrichmentResult":
        return cls(
            provider_id=payload["provider_id"],
            cache_key=payload["cache_key"],
            enrichment_data=payload.get("enrichment_data", {}),
            aliases=[AliasMapping(**alias) for alias in payload.get("aliases", [])],
            timeline_reply=payload.get("timeline_reply"),
            ttl_seconds=payload.get("ttl_seconds"),
        )


class EnrichmentProvider(ABC):
    """Base contract for all enrichment providers."""

    provider_id: str
    display_name: str
    settings_prefix: str
    supported_item_types: Sequence[str]
    supports_bulk_sync: bool = False
    cacheable: bool = True

    @staticmethod
    def _require_record_mapping(record: Any) -> Dict[str, Any]:
        """Return a JSON record mapping or raise the expected record-data error."""
        if not isinstance(record, dict):
            raise MalformedProviderRecordError("Provider record must be an object")
        return record

    @staticmethod
    def _optional_string_field(record: Dict[str, Any], field_name: str) -> str:
        """Read an optional JSON string without masking unrelated code defects."""
        value = record.get(field_name)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise MalformedProviderRecordError(
                f"Provider record field {field_name!r} must be a string"
            )
        return value

    @staticmethod
    def _optional_string_list_field(
        record: Dict[str, Any],
        field_name: str,
    ) -> List[str]:
        """Read an optional list of JSON strings from a provider record."""
        value = record.get(field_name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise MalformedProviderRecordError(
                f"Provider record field {field_name!r} must be a list of strings"
            )
        return value

    @staticmethod
    def _build_user_cache_key_from_values(*values: Any) -> str:
        """Build a normalized user key from the first usable provider identifier."""
        for value in values:
            if isinstance(value, str) and value.strip():
                return f"user:{value.strip().lower()}"
        raise MalformedProviderRecordError(
            "Provider record does not contain a usable user identifier"
        )

    @staticmethod
    def _parse_oauth_access_token_response(
        payload: Any,
        *,
        provider_name: str,
    ) -> tuple[str, int]:
        """Validate the fields shared by OAuth access-token responses."""
        if not isinstance(payload, dict):
            raise EnrichmentProviderError(
                f"{provider_name} token response must be an object"
            )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise EnrichmentProviderError(
                f"{provider_name} token response missing access_token"
            )
        try:
            expires_in = int(payload.get("expires_in") or 3600)
        except (TypeError, ValueError) as exc:
            raise EnrichmentProviderError(
                f"{provider_name} token response has invalid expires_in"
            ) from exc
        return access_token.strip(), expires_in

    @staticmethod
    def _get_normalized_identifier(item: Dict[str, Any], fields: Sequence[str]) -> str:
        for field_name in fields:
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return ""

    def _get_user_identifier(self, item: Dict[str, Any]) -> str:
        return self._get_normalized_identifier(item, ("user_id", "contact_email", "name"))

    async def _get_setting_values(
        self,
        settings: SettingsService,
        names: Sequence[str],
    ) -> Dict[str, Any]:
        """Resolve registered provider-relative settings in one database query."""
        namespaced_defaults = {
            f"{self.settings_prefix}.{name}": self._get_setting_default(name)
            for name in names
        }
        resolved = await settings.get_many(namespaced_defaults)
        return {
            name: resolved[f"{self.settings_prefix}.{name}"]
            for name in names
        }

    def _get_setting_default(self, name: str) -> Any:
        """Return this provider's canonical default for a relative setting name."""
        return get_setting_default(f"{self.settings_prefix}.{name}")

    @staticmethod
    def _build_alias_mappings(
        *,
        entity_type: str,
        canonical_value: str,
        canonical_display: str | None,
        attributes: Dict[str, Any],
        aliases: Iterable[tuple[str, str]],
    ) -> List[AliasMapping]:
        """Build provider aliases while consistently omitting empty values."""
        return [
            AliasMapping(
                entity_type=entity_type,
                canonical_value=canonical_value,
                canonical_display=canonical_display,
                alias_type=alias_type,
                alias_value=alias_value,
                attributes=attributes,
            )
            for alias_type, alias_value in aliases
            if alias_value
        ]

    @abstractmethod
    def can_enrich(self, item: Dict[str, Any]) -> bool:
        """Return True when this provider can enrich the given item."""

    @abstractmethod
    def build_cache_key(self, item: Dict[str, Any]) -> str:
        """Return the provider-specific cache key for the given item."""

    @abstractmethod
    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        """Perform enrichment for the given item."""

    async def bulk_sync(self, *, db: AsyncSession, settings: SettingsService) -> List[EnrichmentResult]:
        """Optional provider-wide synchronization entry point."""
        raise NotImplementedError(f"Provider {self.provider_id} does not support bulk sync")


class UserDirectoryEnrichmentProvider(EnrichmentProvider):
    """Shared matching and cache-key contract for internal user directories."""

    supported_item_types = ("internal_actor",)

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return item.get("type") == "internal_actor" and bool(
            self._get_user_identifier(item)
        )

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        identifier = self._get_user_identifier(item)
        if not identifier:
            raise EnrichmentProviderError(
                f"Cannot determine identifier for {self.display_name} cache key"
            )
        return f"user:{identifier}"
