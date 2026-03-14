from __future__ import annotations

from typing import Dict, List, Optional

from app.services.enrichment.base import EnrichmentProvider


class EnrichmentRegistry:
    """In-process registry for enrichment providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, EnrichmentProvider] = {}

    def register(self, provider: EnrichmentProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> Optional[EnrichmentProvider]:
        return self._providers.get(provider_id)

    def list(self) -> List[EnrichmentProvider]:
        return list(self._providers.values())

    def get_providers_for_item(self, item: dict) -> List[EnrichmentProvider]:
        return [provider for provider in self._providers.values() if provider.can_enrich(item)]


enrichment_registry = EnrichmentRegistry()