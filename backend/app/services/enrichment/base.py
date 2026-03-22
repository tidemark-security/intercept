from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import SettingsService


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