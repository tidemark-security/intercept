from app.services.enrichment import providers
from app.services.enrichment.registry import EnrichmentRegistry


def test_register_providers_is_idempotent_after_registry_reset(monkeypatch) -> None:
    registry = EnrichmentRegistry()
    monkeypatch.setattr(providers, "enrichment_registry", registry)

    providers.register_providers()
    providers.register_providers()

    assert registry.list() == list(providers.BUILTIN_PROVIDERS)
