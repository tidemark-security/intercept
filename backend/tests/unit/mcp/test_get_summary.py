from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.mcp import tools as mcp_tools
from app.models.models import Case
from app.services import mcp_service


def _assert_no_none_values(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert value is not None, f"Unexpected None value for key '{key}'"
            _assert_no_none_values(value)
        return

    if isinstance(payload, list):
        for value in payload:
            assert value is not None, "Unexpected None value in list"
            _assert_no_none_values(value)


@pytest.mark.asyncio
async def test_get_summary_includes_observable_items_from_timeline(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Observable extraction case",
        created_by="analyst",
        timeline_items=[
            {
                "id": "observable-ip-1",
                "type": "observable",
                "timestamp": "2026-03-09T11:38:09.676066+00:00",
                "observable_type": "IP",
                "observable_value": "81.2.69.160",
                "description": "Command-and-control endpoint observed during triage.",
                "enrichment_status": "complete",
                "enrichments": {
                    "maxmind": {
                        "results": {
                            "81.2.69.160": {
                                "databases": {
                                    "GeoLite2-ASN": {
                                        "autonomous_system_organization": "Example ISP"
                                    }
                                }
                            }
                        }
                    }
                },
            }
        ],
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.get_summary(
            db=session,
            kind="case",
            id_str=str(case.id),
            max_observables=10,
        )

    assert result.human_id == "CAS-0000001"
    assert result.timeline.total_count == 1
    assert result.timeline.items[0].preview == "81.2.69.160: Command-and-control endpoint observed during triage."
    assert result.timeline.items[0].observable_type == "IP"
    assert result.timeline.items[0].observable_value == "81.2.69.160"
    assert result.timeline.items[0].enrichment_status == "complete"
    assert result.timeline.items[0].enrichments == {
        "maxmind": {
            "results": {
                "81.2.69.160": {
                    "databases": {
                        "GeoLite2-ASN": {
                            "autonomous_system_organization": "Example ISP"
                        }
                    }
                }
            }
        }
    }
    assert len(result.observables.items) == 1
    assert result.observables.total_count == 1
    assert result.observables.items[0].type == "IP"
    assert result.observables.items[0].value == "81.2.69.160"
    assert result.observables.items[0].count == 1


@pytest.mark.asyncio
async def test_get_summary_exposes_enrichments_for_non_observable_timeline_items(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    case = Case(
        title="Network traffic enrichment case",
        created_by="analyst",
        timeline_items=[
            {
                "id": "network-traffic-1",
                "type": "network_traffic",
                "timestamp": "2026-03-09T11:38:09.676066+00:00",
                "description": "Outbound TLS session to suspicious infrastructure.",
                "source_ip": "10.0.1.100",
                "destination_ip": "203.0.113.50",
                "domain": "evil.example.com",
                "enrichment_status": "complete",
                "enrichments": {
                    "maxmind": {
                        "results": {
                            "203.0.113.50": {
                                "databases": {
                                    "GeoLite2-Country": {
                                        "country": {"iso_code": "GB"}
                                    }
                                }
                            }
                        }
                    }
                },
            }
        ],
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

        result = await mcp_service.get_summary(
            db=session,
            kind="case",
            id_str=str(case.id),
            max_observables=10,
        )

    assert result.timeline.total_count == 1
    assert result.timeline.items[0].type == "network_traffic"
    assert result.timeline.items[0].preview == "Outbound TLS session to suspicious infrastructure."
    assert result.timeline.items[0].enrichment_status == "complete"
    assert result.timeline.items[0].enrichments == {
        "maxmind": {
            "results": {
                "203.0.113.50": {
                    "databases": {
                        "GeoLite2-Country": {
                            "country": {"iso_code": "GB"}
                        }
                    }
                }
            }
        }
    }


@pytest.mark.asyncio
async def test_get_summary_tool_omits_none_values_recursively(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case(
        title="Minimal summary payload case",
        created_by="analyst",
        timeline_items=[
            {
                "id": "observable-ip-2",
                "type": "observable",
                "timestamp": "2026-03-09T11:38:09.676066+00:00",
                "observable_type": "IP",
                "observable_value": "198.51.100.24",
                "description": "Observed in email delivery logs.",
                "enrichment_status": "complete",
                "enrichments": {
                    "maxmind": {
                        "results": {
                            "198.51.100.24": {
                                "databases": {
                                    "GeoLite2-City": {
                                        "city": {"name": None},
                                        "country": {"name": "United States", "iso_code": "US"},
                                        "location": {
                                            "latitude": 37.751,
                                            "longitude": -97.822,
                                            "time_zone": "America/Chicago",
                                            "metro_code": None,
                                        },
                                        "represented_country": {
                                            "name": None,
                                            "iso_code": None,
                                        },
                                        "subdivisions": [],
                                    }
                                },
                                "queried_at": "2026-03-25T12:18:08.194466+00:00",
                            }
                        },
                        "office": "",
                    }
                },
            },
            {
                "id": "note-1",
                "type": "note",
                "timestamp": "2026-03-09T11:39:09.676066+00:00",
                "description": "Analyst confirmed correlation with external telemetry.",
            },
        ],
    )

    async with session_maker() as session:
        session.add(case)
        await session.commit()
        await session.refresh(case)

        assert case.id is not None

    monkeypatch.setattr(mcp_tools, "async_session_factory", session_maker)

    payload = await mcp_tools.get_summary_tool(
        kind="case",
        id=str(case.id),
        max_timeline_items=10,
        max_observables=10,
    )

    _assert_no_none_values(payload)
    note_item = next(item for item in payload["timeline"]["items"] if item["type"] == "note")
    observable_item = next(item for item in payload["timeline"]["items"] if item["type"] == "observable")
    assert "author" not in note_item
    assert "entity_id" not in note_item
    assert "office" not in observable_item["enrichments"]["maxmind"]
    city_db = observable_item["enrichments"]["maxmind"]["results"]["198.51.100.24"]["databases"]["GeoLite2-City"]
    assert "subdivisions" not in city_db
    assert "represented_country" not in city_db
    assert "city" not in city_db
    assert "metro_code" not in city_db["location"]