from datetime import datetime, timezone
from typing import Any

import pytest

from app.models.enums import AlertStatus, Priority
from app.models.models import Alert
from app.services.similarity_service import find_related_alerts


def _alert(*, title: str, source: str | None, timeline_items: dict | None = None) -> Alert:
    now = datetime.now(timezone.utc)
    return Alert(
        title=title,
        description="Similarity service test",
        source=source,
        priority=Priority.MEDIUM,
        status=AlertStatus.NEW,
        created_at=now,
        updated_at=now,
        timeline_items=timeline_items or {},
    )


@pytest.mark.asyncio
async def test_source_less_seed_only_matches_source_less_alerts(session_maker: Any) -> None:
    seed = _alert(title="PowerShell Execution", source=None)
    matching = _alert(title="PowerShell execution", source=None)
    other_source = _alert(title="PowerShell execution", source="SIEM")

    async with session_maker() as session:
        session.add_all([seed, matching, other_source])
        await session.commit()
        results = await find_related_alerts(session, seed)

    assert [result["alert"].id for result in results] == [matching.id]


@pytest.mark.asyncio
async def test_shared_entity_reasons_are_deterministic(session_maker: Any) -> None:
    timeline_items = {
        value: {
            "id": value,
            "type": "observable",
            "observable_type": "DOMAIN",
            "observable_value": value,
        }
        for value in ("c.example.com", "a.example.com", "b.example.com", "d.example.com")
    }
    seed = _alert(title="Malware callback", source="SIEM", timeline_items=timeline_items)
    matching = _alert(title="Malware callback", source="SIEM", timeline_items=timeline_items)

    async with session_maker() as session:
        session.add_all([seed, matching])
        await session.commit()
        results = await find_related_alerts(session, seed)

    assert results[0]["reasons"] == [
        "same_source_title",
        "shared_domain:a.example.com",
        "shared_domain:b.example.com",
        "shared_domain:c.example.com",
    ]
