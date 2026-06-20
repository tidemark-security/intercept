from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from app.models.models import LinkTemplate
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login(client: AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {get_local("auth.session.cookie_name"): response.cookies[get_local("auth.session.cookie_name")]}


async def _seed_template(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    template_id: str = "crowdstrike-device",
    url_template: str = "https://falcon.example/devices/{{user.cid}}/{{device.hostname}}",
    tooltip_template: str = "Open {{device.hostname}} in {{user.tenant}}",
) -> int:
    async with session_maker() as session:
        template = LinkTemplate(
            template_id=template_id,
            name="CrowdStrike Device",
            icon_name="CrowdStrikeIcon",
            tooltip_template=tooltip_template,
            url_template=url_template,
            field_names=["device.hostname"],
            conditions={"type": "host"},
            enabled=True,
            display_order=10,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template.id


async def test_user_preferences_are_owned_by_current_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    first_user = analyst_user_factory(username="analyst_one")
    second_user = analyst_user_factory(username="analyst_two")
    async with session_maker() as session:
        session.add_all([first_user, second_user])
        await session.commit()

    template_pk = await _seed_template(session_maker)
    first_cookies = await _login(client, first_user.username)
    second_cookies = await _login(client, second_user.username)

    upsert_response = await client.put(
        f"/api/v1/link-templates/user-preferences/{template_pk}",
        json={"enabled": True, "values": {"cid": "abc123", "tenant": "Falcon"}},
        cookies=first_cookies,
    )
    assert upsert_response.status_code == 200, upsert_response.text

    first_list = await client.get("/api/v1/link-templates/user-preferences", cookies=first_cookies)
    second_list = await client.get("/api/v1/link-templates/user-preferences", cookies=second_cookies)
    assert len(first_list.json()) == 1
    assert second_list.json() == []


async def test_resolve_interpolates_context_and_user_values(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(username="analyst_resolve")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    template_pk = await _seed_template(session_maker)
    cookies = await _login(client, user.username)
    await client.put(
        f"/api/v1/link-templates/user-preferences/{template_pk}",
        json={"enabled": True, "values": {"cid": "tenant 1", "tenant": "Falcon Console"}},
        cookies=cookies,
    )

    response = await client.post(
        "/api/v1/link-templates/resolve",
        json={"item": {"type": "host", "device": {"hostname": "host 01"}}},
        cookies=cookies,
    )
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": template_pk,
            "template_id": "crowdstrike-device",
            "name": "CrowdStrike Device",
            "icon_name": "CrowdStrikeIcon",
            "tooltip": "Open host 01 in Falcon Console",
            "url": "https://falcon.example/devices/tenant%201/host%2001",
            "display_order": 10,
        }
    ]


async def test_resolve_skips_disabled_or_incomplete_templates(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(username="analyst_disabled")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    template_pk = await _seed_template(session_maker)
    cookies = await _login(client, user.username)

    missing_values_response = await client.post(
        "/api/v1/link-templates/resolve",
        json={"item": {"type": "host", "device": {"hostname": "host01"}}},
        cookies=cookies,
    )
    assert missing_values_response.status_code == 200, missing_values_response.text
    assert missing_values_response.json() == []

    await client.put(
        f"/api/v1/link-templates/user-preferences/{template_pk}",
        json={"enabled": False, "values": {"cid": "abc123", "tenant": "Falcon"}},
        cookies=cookies,
    )
    disabled_response = await client.post(
        "/api/v1/link-templates/resolve",
        json={"item": {"type": "host", "device": {"hostname": "host01"}}},
        cookies=cookies,
    )
    assert disabled_response.status_code == 200, disabled_response.text
    assert disabled_response.json() == []
