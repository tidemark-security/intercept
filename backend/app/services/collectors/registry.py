"""In-process collector registry and provider setting registration."""

from __future__ import annotations

import re

from app.core.settings_registry import SETTINGS_REGISTRY, SettingDefinition
from app.models.enums import SettingType
from app.services.collectors.base import CollectorProvider

PROVIDER_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _setting(
    key: str,
    *,
    value_type: SettingType = SettingType.STRING,
    default=None,
    description: str,
) -> SettingDefinition:
    return SettingDefinition(
        key=key,
        env_var=key.upper().replace(".", "__"),
        value_type=value_type,
        default=default,
        category="collectors",
        description=description,
    )


def common_provider_settings(provider: CollectorProvider) -> tuple[SettingDefinition, ...]:
    prefix = f"collectors.{provider.provider_id}"
    label = provider.display_name
    return (
        _setting(f"{prefix}.enabled", value_type=SettingType.BOOLEAN, default=False, description=f"Enable {label} collection"),
        _setting(f"{prefix}.schedule_enabled", value_type=SettingType.BOOLEAN, default=False, description=f"Enable daily scheduled collection for {label}"),
        _setting(f"{prefix}.schedule_time_utc", default="", description=f"Daily {label} collection time in HH:MM UTC"),
        _setting(f"{prefix}.page_size", value_type=SettingType.NUMBER, default=100, description=f"Maximum {label} events requested per page"),
        _setting(f"{prefix}.max_pages_per_run", value_type=SettingType.NUMBER, default=100, description=f"Maximum {label} pages processed per run"),
        _setting(f"{prefix}.request_timeout_seconds", value_type=SettingType.NUMBER, default=30, description=f"Network timeout for {label} requests"),
        _setting(f"{prefix}.overlap_seconds", value_type=SettingType.NUMBER, default=300, description=f"Timestamp checkpoint overlap for {label}"),
        _setting(f"{prefix}.triage_policy", default="standard", description=f"Default Intercept triage policy for {label} findings"),
    )


class CollectorRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, CollectorProvider] = {}

    def register(self, provider: CollectorProvider) -> None:
        if not PROVIDER_ID_RE.fullmatch(provider.provider_id):
            raise ValueError("Collector provider_id must contain only lowercase letters, numbers, and underscores")
        expected_prefix = f"collectors.{provider.provider_id}"
        if provider.settings_prefix != expected_prefix:
            raise ValueError(f"Collector settings_prefix must be {expected_prefix!r}")
        if not getattr(provider, "alert_source", "").strip():
            raise ValueError("Collector alert_source must be a stable non-empty grouping value")
        if provider.provider_id in self._providers and self._providers[provider.provider_id] is not provider:
            raise ValueError(f"Collector provider {provider.provider_id!r} is already registered")

        for definition in (*common_provider_settings(provider), *provider.setting_definitions):
            if not definition.key.startswith(f"{expected_prefix}."):
                raise ValueError("Provider settings must be scoped below settings_prefix")
            existing = SETTINGS_REGISTRY.get(definition.key)
            if existing is not None and existing != definition:
                raise ValueError(f"Setting {definition.key!r} is already registered differently")
            SETTINGS_REGISTRY[definition.key] = definition

        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> CollectorProvider | None:
        return self._providers.get(provider_id)

    def require(self, provider_id: str) -> CollectorProvider:
        provider = self.get(provider_id)
        if provider is None:
            raise ValueError(f"Collector provider {provider_id!r} is not registered")
        return provider

    def list(self) -> list[CollectorProvider]:
        return list(self._providers.values())


collector_registry = CollectorRegistry()

