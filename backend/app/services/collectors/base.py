"""Base contract implemented by in-process alert collector providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from app.core.settings_registry import SettingDefinition
from app.services.collectors.models import (
    CollectionPage,
    CollectorContext,
    EvaluationResult,
    ExternalEvent,
    NormalizedEvent,
    ValidationRequest,
    ValidationResult,
)


class CollectorProvider(ABC):
    provider_id: str
    display_name: str
    settings_prefix: str
    alert_source: str
    processor_version: str = "1"
    stream_keys: Sequence[str] = ("default",)
    allowed_url_hosts: Sequence[str] = ()
    allowed_validation_assessments: Sequence[str] = ()
    setting_definitions: Sequence[SettingDefinition] = ()

    @abstractmethod
    async def fetch_page(
        self,
        *,
        checkpoint: dict | None,
        context: CollectorContext,
    ) -> CollectionPage:
        """Fetch one bounded page without changing durable state."""

    @abstractmethod
    def normalize(self, event: ExternalEvent) -> NormalizedEvent:
        """Convert untrusted provider data into the bounded common schema."""

    @abstractmethod
    async def evaluate(
        self,
        *,
        event: NormalizedEvent,
        context: CollectorContext,
    ) -> EvaluationResult:
        """Produce findings, a durable skip, or a validation request."""

    async def request_validation(
        self,
        *,
        request: ValidationRequest,
        context: CollectorContext,
    ) -> None:
        """Optionally invoke an external validator after the request is durable."""

        return None

    async def test_connection(self, *, context: CollectorContext) -> CollectionPage:
        """Perform a bounded, read-only provider check."""

        return await self.fetch_page(checkpoint=None, context=context)

    def validate_validation_result(self, result: "ValidationResult") -> None:
        """Apply provider-specific assessment and evidence policy to a callback."""

        if (
            self.allowed_validation_assessments
            and result.assessment not in self.allowed_validation_assessments
        ):
            raise ValueError("Validation assessment is not allowed for this provider")
