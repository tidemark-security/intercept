from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from app.models.models import LinkTemplate, PersonalLinkTemplate
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login(client: AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {get_local("auth.session.cookie_name"): response.cookies[get_local("auth.session.cookie_name")]}


def _template_payload(**overrides):
    payload = {
        "template_id": "case-console",
        "name": "Case Console",
        "icon_name": "Link2",
        "tooltip_template": "Open {{human_id}}",
        "url_template": "https://console.example/cases/{{human_id}}",
        "field_names": ["human_id"],
        "conditions": None,
        "surface_scopes": ["entity"],
        "entity_types": ["case"],
        "enabled": True,
        "display_order": 10,
    }
    payload.update(overrides)
    return payload


async def test_personal_link_templates_are_owned_by_current_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    first_user = analyst_user_factory(username="analyst_personal_one")
    second_user = analyst_user_factory(username="analyst_personal_two")
    async with session_maker() as session:
        session.add_all([first_user, second_user])
        await session.commit()

    first_cookies = await _login(client, first_user.username)
    second_cookies = await _login(client, second_user.username)

    create_response = await client.post(
        "/api/v1/personal-link-templates",
        json=_template_payload(template_id="my-case-console", name="My Case Console"),
        cookies=first_cookies,
    )
    assert create_response.status_code == 200, create_response.text

    first_list = await client.get("/api/v1/personal-link-templates", cookies=first_cookies)
    second_list = await client.get("/api/v1/personal-link-templates", cookies=second_cookies)
    assert [template["template_id"] for template in first_list.json()] == ["my-case-console"]
    assert second_list.json() == []


async def test_resolve_merges_public_and_current_user_personal_templates_with_scope_filtering(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(username="analyst_link_resolve")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

        session.add_all(
            [
                LinkTemplate(
                    **_template_payload(
                        template_id="public-case-console",
                        name="Public Case Console",
                        display_order=20,
                    )
                ),
                PersonalLinkTemplate(
                    **_template_payload(
                        template_id="personal-case-console",
                        name="Personal Case Console",
                        display_order=10,
                    ),
                    user_id=user.id,
                ),
                LinkTemplate(
                    **_template_payload(
                        template_id="timeline-only",
                        name="Timeline Only",
                        surface_scopes=["timeline_item"],
                        entity_types=["alert"],
                        conditions={"type": "observable"},
                        field_names=["observable_value"],
                        tooltip_template="Search {{observable_value}}",
                        url_template="https://intel.example/{{observable_value}}",
                        display_order=30,
                    )
                ),
            ]
        )
        await session.commit()

    cookies = await _login(client, user.username)

    entity_response = await client.post(
        "/api/v1/link-templates/resolve",
        json={
            "surface": "entity",
            "entity_type": "case",
            "item": {"human_id": "CASE-101", "title": "Interesting case"},
        },
        cookies=cookies,
    )
    assert entity_response.status_code == 200, entity_response.text
    assert [
        (link["visibility"], link["template_id"], link["url"])
        for link in entity_response.json()
    ] == [
        ("PERSONAL", "personal-case-console", "https://console.example/cases/CASE-101"),
        ("PUBLIC", "public-case-console", "https://console.example/cases/CASE-101"),
    ]

    timeline_response = await client.post(
        "/api/v1/link-templates/resolve",
        json={
            "surface": "timeline_item",
            "entity_type": "alert",
            "item": {"type": "observable", "observable_value": "example.com"},
        },
        cookies=cookies,
    )
    assert timeline_response.status_code == 200, timeline_response.text
    assert [link["template_id"] for link in timeline_response.json()] == ["timeline-only"]


async def test_import_export_supports_copy_conflicts_and_destination_ownership(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
):
    admin = admin_user_factory(username="admin_link_import")
    analyst = analyst_user_factory(username="analyst_link_import")
    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    admin_cookies = await _login(client, admin.username)
    analyst_cookies = await _login(client, analyst.username)

    bundle = {"schema_version": 1, "templates": [_template_payload(template_id="shared-console")]}
    first_import = await client.post("/api/v1/link-templates/import", json=bundle, cookies=admin_cookies)
    second_import = await client.post("/api/v1/link-templates/import", json=bundle, cookies=admin_cookies)
    assert first_import.status_code == 200, first_import.text
    assert second_import.status_code == 200, second_import.text

    first_template = first_import.json()[0]
    copied_template = second_import.json()[0]
    assert first_template["template_id"] == "shared-console"
    assert copied_template["template_id"] == "shared-console-copy"
    assert copied_template["name"] == "Case Console (copy)"

    export_response = await client.post(
        "/api/v1/link-templates/export",
        json={"template_ids": [first_template["id"]]},
        cookies=admin_cookies,
    )
    assert export_response.status_code == 200, export_response.text
    exported = export_response.json()
    assert exported["schema_version"] == 1
    assert exported["templates"][0]["template_id"] == "shared-console"
    assert "id" not in exported["templates"][0]
    assert "user_id" not in exported["templates"][0]

    personal_import = await client.post(
        "/api/v1/personal-link-templates/import",
        json=exported,
        cookies=analyst_cookies,
    )
    assert personal_import.status_code == 200, personal_import.text
    assert personal_import.json()[0]["template_id"] == "shared-console"
    assert personal_import.json()[0]["user_id"] == str(analyst.id)


async def test_import_accepts_single_template_and_bare_array_payloads(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
):
    admin = admin_user_factory(username="admin_link_import_shapes")
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    admin_cookies = await _login(client, admin.username)

    single_response = await client.post(
        "/api/v1/link-templates/import",
        json=_template_payload(template_id="single-console", name="Single Console"),
        cookies=admin_cookies,
    )
    array_response = await client.post(
        "/api/v1/link-templates/import",
        json=[_template_payload(template_id="array-console", name="Array Console")],
        cookies=admin_cookies,
    )

    assert single_response.status_code == 200, single_response.text
    assert array_response.status_code == 200, array_response.text
    assert single_response.json()[0]["template_id"] == "single-console"
    assert array_response.json()[0]["template_id"] == "array-console"


async def test_public_and_personal_templates_reject_multiple_surface_scopes(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
):
    admin = admin_user_factory(username="admin_link_surface_scope")
    analyst = analyst_user_factory(username="analyst_link_surface_scope")
    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    admin_cookies = await _login(client, admin.username)
    analyst_cookies = await _login(client, analyst.username)
    payload = _template_payload(surface_scopes=["timeline_item", "entity"])

    public_response = await client.post("/api/v1/link-templates", json=payload, cookies=admin_cookies)
    personal_response = await client.post("/api/v1/personal-link-templates", json=payload, cookies=analyst_cookies)
    import_response = await client.post(
        "/api/v1/link-templates/import",
        json={"schema_version": 1, "templates": [payload]},
        cookies=admin_cookies,
    )

    assert public_response.status_code == 422
    assert personal_response.status_code == 422
    assert import_response.status_code == 422


async def test_legacy_user_preferences_route_is_removed(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
):
    user = analyst_user_factory(username="analyst_no_preferences")
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    cookies = await _login(client, user.username)
    response = await client.get("/api/v1/link-templates/user-preferences", cookies=cookies)
    assert response.status_code >= 400
