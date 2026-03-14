"""Enrichment provider package."""

from app.services.enrichment.providers.entra_id import entra_id_provider
from app.services.enrichment.providers.google_workspace import google_workspace_provider
from app.services.enrichment.providers.ldap_provider import ldap_provider
from app.services.enrichment.providers.maxmind import maxmind_provider
from app.services.enrichment.registry import enrichment_registry

_REGISTERED = False


def register_providers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    for provider in (
        entra_id_provider,
        google_workspace_provider,
        ldap_provider,
        maxmind_provider,
    ):
        if enrichment_registry.get(provider.provider_id) is None:
            enrichment_registry.register(provider)

    _REGISTERED = True


__all__ = [
    "entra_id_provider",
    "google_workspace_provider",
    "ldap_provider",
    "maxmind_provider",
    "register_providers",
]