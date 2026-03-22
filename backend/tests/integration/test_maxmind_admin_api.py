from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AppSetting
from app.services.maxmind_service import maxmind_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_admin(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> str:
    admin = admin_user_factory()

    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200

    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_admin_maxmind_database_status_degrades_when_storage_unavailable(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_admin(client, session_maker, admin_user_factory)

    async def fail_ensure_bucket() -> None:
        raise ConnectionError("storage unavailable")

    monkeypatch.setattr(maxmind_service, "_ensure_bucket", fail_ensure_bucket)

    response = await client.get(
        "/api/v1/admin/enrichments/maxmind/databases",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()

    assert [item["edition_id"] for item in data] == [
        "GeoLite2-ASN",
        "GeoLite2-City",
        "GeoLite2-Country",
    ]
    assert all(item["available_in_storage"] is False for item in data)
    assert all(item["loaded"] is False for item in data)
    assert all(item["local_path"] is None for item in data)
    assert all(item["file_size_bytes"] is None for item in data)
    assert all(item["last_updated"] is None for item in data)
    assert all(item["content_sha256"] is None for item in data)


@pytest.mark.asyncio
async def test_admin_maxmind_database_status_ignores_invalid_edition_ids(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    session_cookie = await _login_admin(client, session_maker, admin_user_factory)

    async with session_maker() as session:
        session.add(
            AppSetting(
                key="enrichment.maxmind.edition_ids",
                value='["pee pee"]',
                value_type="JSON",
                is_secret=False,
                description="",
                category="enrichment",
            )
        )
        await session.commit()

    response = await client.get(
        "/api/v1/admin/enrichments/maxmind/databases",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert response.json() == []