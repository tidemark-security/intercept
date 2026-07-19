"""Enrichment provider package."""

from app.services.enrichment.providers.cross_case_observable import cross_case_observable_provider
from app.services.enrichment.providers.entra_id import entra_id_provider
from app.services.enrichment.providers.google_workspace import google_workspace_provider
from app.services.enrichment.providers.ldap_provider import ldap_provider
from app.services.enrichment.providers.maxmind import maxmind_provider
from app.services.enrichment.providers.servicenow import servicenow_provider
from app.services.enrichment.registry import enrichment_registry

BUILTIN_PROVIDERS = (
    cross_case_observable_provider,
    entra_id_provider,
    google_workspace_provider,
    ldap_provider,
    maxmind_provider,
    servicenow_provider,
)


def register_providers() -> None:
    for provider in BUILTIN_PROVIDERS:
        if enrichment_registry.get(provider.provider_id) is None:
            enrichment_registry.register(provider)


__all__ = [
    "entra_id_provider",
    "cross_case_observable_provider",
    "google_workspace_provider",
    "ldap_provider",
    "maxmind_provider",
    "servicenow_provider",
    "BUILTIN_PROVIDERS",
    "register_providers",
]
