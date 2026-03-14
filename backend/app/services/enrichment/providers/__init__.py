"""Enrichment provider package.

Providers are registered with ``enrichment_registry`` on import.
"""
from app.services.enrichment.providers.entra_id import entra_id_provider
from app.services.enrichment.providers.google_workspace import google_workspace_provider
from app.services.enrichment.providers.ldap_provider import ldap_provider
from app.services.enrichment.registry import enrichment_registry

enrichment_registry.register(entra_id_provider)
enrichment_registry.register(google_workspace_provider)
enrichment_registry.register(ldap_provider)

__all__ = [
    "entra_id_provider",
    "google_workspace_provider",
    "ldap_provider",
]