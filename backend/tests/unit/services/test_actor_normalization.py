from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActorType
from app.models.models import Actor, ActorSnapshot
from app.services.normalization_service import normalization_service


@pytest.mark.asyncio
async def test_normalize_actor_snapshots_external_display_name_alias(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        normalized = await normalization_service.normalize_item(
            session,
            {
                'id': 'actor-ingested-1',
                'type': 'internal_actor',
                'display_name': 'External Payload User',
                'username': 'external.user',
                'created_at': '2026-05-24T00:00:00Z',
            },
        )
        await session.commit()

    async with session_maker() as session:
        denormalized = await normalization_service.denormalize_item(session, normalized)

    assert denormalized['name'] == 'External Payload User'
    assert denormalized['user_id'] == 'external.user'


@pytest.mark.asyncio
async def test_denormalize_actor_coalesces_google_workspace_fields_without_overriding_snapshot(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        actor = Actor(
            actor_type=ActorType.INTERNAL,
            user_id='glenn@glennjamin.com',
            name=None,
            title=None,
            org=None,
            contact_phone=None,
            contact_email=None,
        )
        session.add(actor)
        await session.flush()
        assert actor.id is not None

        snapshot = ActorSnapshot(
            actor_id=actor.id,
            snapshot_hash='snapshot-1',
            snapshot={
            'actor_type': ActorType.INTERNAL.value,
                'user_id': 'glenn@glennjamin.com',
                'name': 'Snapshot Name',
                'title': '',
                'org': '',
                'contact_phone': None,
                'contact_email': None,
            },
        )
        session.add(snapshot)
        await session.commit()

    async with session_maker() as session:
        item = {
            'id': 'actor-1',
            'type': 'internal_actor',
            'actor_id': actor.id,
            'snapshot_hash': 'snapshot-1',
            'enrichments': {
                'google_workspace': {
                    'display_name': 'Glenn Bolton',
                    'job_title': 'Principal Consultant',
                    'organization': 'Tidemark',
                    'phone': '+1-555-0100',
                    'primary_email': 'glenn@glennjamin.com',
                }
            },
        }

        denormalized = await normalization_service.denormalize_item(session, item)

    assert denormalized['name'] == 'Snapshot Name'
    assert denormalized['title'] == 'Principal Consultant'
    assert denormalized['org'] == 'Tidemark'
    assert denormalized['contact_phone'] == '+1-555-0100'
    assert denormalized['contact_email'] == 'glenn@glennjamin.com'


@pytest.mark.asyncio
async def test_denormalize_actor_coalesces_google_workspace_fields_from_actor_fallback(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        actor = Actor(
            actor_type=ActorType.INTERNAL,
            user_id='glenn@glennjamin.com',
            name=None,
            title=None,
            org=None,
            contact_phone=None,
            contact_email=None,
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        assert actor.id is not None

    async with session_maker() as session:
        item = {
            'id': 'actor-2',
            'type': 'internal_actor',
            'actor_id': actor.id,
            'enrichments': {
                'google_workspace': {
                    'display_name': 'Glenn Bolton',
                    'job_title': 'Principal Consultant',
                    'organization': 'Tidemark',
                    'phone': '+1-555-0100',
                    'primary_email': 'glenn@glennjamin.com',
                }
            },
        }

        denormalized = await normalization_service.denormalize_item(session, item)

    assert denormalized['name'] == 'Glenn Bolton'
    assert denormalized['title'] == 'Principal Consultant'
    assert denormalized['org'] == 'Tidemark'
    assert denormalized['contact_phone'] == '+1-555-0100'
    assert denormalized['contact_email'] == 'glenn@glennjamin.com'


@pytest.mark.asyncio
async def test_denormalize_actor_coalesces_entra_id_fields_with_fallbacks(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        actor = Actor(
            actor_type=ActorType.INTERNAL,
            user_id='glenn@glennjamin.com',
            name=None,
            title=None,
            org=None,
            contact_phone=None,
            contact_email=None,
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        assert actor.id is not None

    async with session_maker() as session:
        item = {
            'id': 'actor-3',
            'type': 'internal_actor',
            'actor_id': actor.id,
            'enrichments': {
                'entra_id': {
                    'display_name': 'Glenn Bolton',
                    'job_title': 'Principal Consultant',
                    'department': 'Consulting',
                    'office': 'Sydney',
                    'mobile_phone': '',
                    'business_phones': ['+61-2-5550-1000'],
                    'email': '',
                    'upn': 'glenn@glennjamin.com',
                }
            },
        }

        denormalized = await normalization_service.denormalize_item(session, item)

    assert denormalized['name'] == 'Glenn Bolton'
    assert denormalized['title'] == 'Principal Consultant'
    assert denormalized['org'] == 'Consulting'
    assert denormalized['contact_phone'] == '+61-2-5550-1000'
    assert denormalized['contact_email'] == 'glenn@glennjamin.com'


@pytest.mark.asyncio
async def test_denormalize_actor_coalesces_ldap_fields_with_fallbacks(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        actor = Actor(
            actor_type=ActorType.INTERNAL,
            user_id='glenn@glennjamin.com',
            name=None,
            title=None,
            org=None,
            contact_phone=None,
            contact_email=None,
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        assert actor.id is not None

    async with session_maker() as session:
        item = {
            'id': 'actor-4',
            'type': 'internal_actor',
            'actor_id': actor.id,
            'enrichments': {
                'ldap': {
                    'display_name': 'Glenn Bolton',
                    'job_title': 'Principal Consultant',
                    'company': '',
                    'department': 'Incident Response',
                    'office': 'Melbourne',
                    'phone': '',
                    'mobile': '+61-4-1234-5678',
                    'email': 'glenn@glennjamin.com',
                    'upn': 'glenn@glennjamin.com',
                }
            },
        }

        denormalized = await normalization_service.denormalize_item(session, item)

    assert denormalized['name'] == 'Glenn Bolton'
    assert denormalized['title'] == 'Principal Consultant'
    assert denormalized['org'] == 'Incident Response'
    assert denormalized['contact_phone'] == '+61-4-1234-5678'
    assert denormalized['contact_email'] == 'glenn@glennjamin.com'


@pytest.mark.asyncio
async def test_threat_actor_does_not_reuse_external_actor_identity(session_maker: Any) -> None:
    identity = {
        'name': 'Shared Actor Name',
        'org': 'Shared Organization',
    }

    async with session_maker() as session:
        external = await normalization_service.normalize_item(
            session,
            {'id': 'external-1', 'type': 'external_actor', **identity},
        )
        threat = await normalization_service.normalize_item(
            session,
            {'id': 'threat-1', 'type': 'threat_actor', **identity},
        )
        await session.commit()
        external_actor = await session.get(Actor, external['actor_id'])
        threat_actor = await session.get(Actor, threat['actor_id'])

    assert external['actor_id'] != threat['actor_id']
    assert external_actor is not None
    assert external_actor.actor_type == ActorType.EXTERNAL
    assert threat_actor is not None
    assert threat_actor.actor_type == ActorType.EXTERNAL_THREAT


@pytest.mark.asyncio
async def test_actor_id_only_item_snapshots_canonical_actor_fields(session_maker: Any) -> None:
    async with session_maker() as session:
        actor = Actor(
            actor_type=ActorType.EXTERNAL,
            name='Canonical Name',
            title='Incident Contact',
            org='Canonical Organization',
            contact_email='contact@example.com',
        )
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        assert actor.id is not None
        actor_id = actor.id

        normalized = await normalization_service.normalize_item(
            session,
            {'id': 'actor-reference', 'type': 'external_actor', 'actor_id': actor_id},
        )
        await session.commit()

    async with session_maker() as session:
        denormalized = await normalization_service.denormalize_item(session, normalized)

    assert denormalized['name'] == 'Canonical Name'
    assert denormalized['title'] == 'Incident Contact'
    assert denormalized['org'] == 'Canonical Organization'
    assert denormalized['contact_email'] == 'contact@example.com'
