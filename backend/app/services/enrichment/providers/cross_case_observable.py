from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Case
from app.services.enrichment.base import EnrichmentProvider, EnrichmentResult
from app.services.settings_service import SettingsService
from app.services.timeline_service import timeline_service


class CrossCaseObservableProvider(EnrichmentProvider):
    provider_id = "cross_case_observable"
    display_name = "Cross-Case Observable Correlation"
    settings_prefix = "enrichment.cross_case_observable"
    supported_item_types = ("observable",)
    supports_bulk_sync = False

    def can_enrich(self, item: Dict[str, Any]) -> bool:
        return self._observable(item) is not None

    def build_cache_key(self, item: Dict[str, Any]) -> str:
        observable = self._observable(item)
        if observable is None:
            raise ValueError("No observable available for cross-case correlation")
        observable_type, observable_value = observable
        return f"{observable_type}:{observable_value}"

    async def enrich(
        self,
        *,
        db: AsyncSession,
        settings: SettingsService,
        item: Dict[str, Any],
        entity_type: str,
        entity_id: int,
    ) -> EnrichmentResult:
        observable = self._observable(item)
        if observable is None:
            raise ValueError("No observable available for cross-case correlation")
        observable_type, observable_value = observable

        result = await db.execute(select(Case).order_by(Case.updated_at.desc()))
        matches: list[dict[str, Any]] = []
        total = 0
        for case in result.scalars().all():
            if entity_type == "case" and case.id == entity_id:
                continue
            if not self._case_contains_observable(case, observable_type, observable_value):
                continue
            total += 1
            if len(matches) < 5:
                matches.append(
                    {
                        "case_id": case.id,
                        "case_human_id": f"CAS-{case.id:07d}" if case.id is not None else None,
                        "title": case.title,
                        "status": case.status.value if hasattr(case.status, "value") else case.status,
                        "priority": case.priority.value if hasattr(case.priority, "value") else case.priority,
                        "created_at": case.created_at.isoformat() if case.created_at else None,
                        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
                        "closed_at": case.closed_at.isoformat() if case.closed_at else None,
                    }
                )

        ttl_seconds = int(await settings.get("enrichment.cross_case_observable.ttl_seconds", 3600) or 3600)
        return EnrichmentResult(
            provider_id=self.provider_id,
            cache_key=self.build_cache_key(item),
            enrichment_data={
                "observable_type": observable_type,
                "observable_value": observable_value,
                "queried_at": datetime.now(timezone.utc).isoformat(),
                "other_case_count": total,
                "matching_cases": matches,
            },
            ttl_seconds=ttl_seconds,
        )

    def _observable(self, item: Dict[str, Any]) -> tuple[str, str] | None:
        if item.get("type") != "observable":
            return None
        observable_type = str(item.get("observable_type") or "").strip().upper()
        observable_value = str(item.get("observable_value") or "").strip().lower()
        if not observable_type or not observable_value:
            return None
        return observable_type, observable_value

    def _case_contains_observable(self, case: Case, observable_type: str, observable_value: str) -> bool:
        for candidate in timeline_service._iter_items(case.timeline_items or {}):
            if candidate.get("type") != "observable":
                continue
            candidate_type = str(candidate.get("observable_type") or "").strip().upper()
            candidate_value = str(candidate.get("observable_value") or "").strip().lower()
            if candidate_type == observable_type and candidate_value == observable_value:
                return True
        return False


cross_case_observable_provider = CrossCaseObservableProvider()
