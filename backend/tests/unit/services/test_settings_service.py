"""Targeted regression tests for settings refactor behavior."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.core.security import initialize_encryption_service
from app.models.enums import SettingType
from app.models.models import AppSetting, AppSettingCreate
from app.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_create_setting_uses_registry_secret_metadata(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    initialize_encryption_service(b"test-master-key")

    async with session_maker() as session:
        service = SettingsService(session)

        created = await service.create_setting(
            AppSettingCreate(
                key="langflow.api_key",
                value="secret-value",
                value_type=SettingType.STRING,
                is_secret=False,
                description="",
                category="langflow",
            )
        )

        assert created.is_secret is True
        assert created.value is not None
        assert created.value == "***"
        assert "secret-value" not in created.value

        row = (
            await session.execute(
                select(AppSetting).where(AppSetting.key == "langflow.api_key")
            )
        ).scalar_one()
        assert row.is_secret is True
        assert row.value != "secret-value"


@pytest.mark.asyncio
async def test_get_setting_serializes_boolean_default_lowercase(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.delenv("TRIAGE__AUTO_ENQUEUE", raising=False)

    async with session_maker() as session:
        service = SettingsService(session)
        setting = await service.get_setting("triage.auto_enqueue")

        assert setting is not None
        assert setting.source == "default"
        assert setting.value == "false"


@pytest.mark.asyncio
async def test_ad_hoc_setting_resolution_is_consistent_for_single_and_list_reads(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.setenv("LEGACY__SETTING", "environment-value")

    async with session_maker() as session:
        session.add(
            AppSetting(
                key="legacy.setting",
                value="database-value",
                category="legacy",
            )
        )
        await session.commit()

        service = SettingsService(session)
        single = await service.get_setting("legacy.setting")
        listed = await service.get_all_settings(category="legacy")

        assert single is not None
        assert len(listed) == 1
        assert listed[0].model_dump() == single.model_dump()
        assert single.source == "env"
        assert single.value == "environment-value"


@pytest.mark.asyncio
async def test_get_many_matches_single_setting_precedence(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRIAGE__AUTO_ENQUEUE", "true")
    monkeypatch.delenv("LANGFLOW__DEFAULT_FLOW_ID", raising=False)

    async with session_maker() as session:
        session.add(
            AppSetting(
                key="langflow.default_flow_id",
                value="database-flow",
                category="langflow",
            )
        )
        await session.commit()

        service = SettingsService(session)
        values = await service.get_many(
            {
                "triage.auto_enqueue": False,
                "langflow.default_flow_id": "fallback-flow",
                "unknown.setting": "caller-default",
            }
        )

        assert values == {
            "triage.auto_enqueue": True,
            "langflow.default_flow_id": "database-flow",
            "unknown.setting": "caller-default",
        }


@pytest.mark.asyncio
async def test_get_many_matches_get_for_legacy_secret_metadata(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.delenv("LANGFLOW__API_KEY", raising=False)

    async with session_maker() as session:
        session.add(
            AppSetting(
                key="langflow.api_key",
                value="legacy-plaintext",
                value_type=SettingType.STRING,
                is_secret=False,
                category="langflow",
            )
        )
        await session.commit()

        service = SettingsService(session)

        assert await service.get("langflow.api_key") == "legacy-plaintext"
        assert await service.get_many({"langflow.api_key": "fallback"}) == {
            "langflow.api_key": "legacy-plaintext"
        }
