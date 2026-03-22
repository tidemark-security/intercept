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
        assert "****" in created.value
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
