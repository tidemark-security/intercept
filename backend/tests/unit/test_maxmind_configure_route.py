from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import enrichments
from app.models.models import AppSettingCreate, MaxMindConfigureRequest


class _FakeSettingsService:
    saved_keys: list[str] = []

    def __init__(self, _db: object) -> None:
        pass

    async def upsert_setting_in_transaction(
        self,
        setting_create: AppSettingCreate,
        **_kwargs: object,
    ) -> object:
        self.saved_keys.append(setting_create.key)
        return SimpleNamespace(key=setting_create.key)


@pytest.mark.asyncio
async def test_configure_maxmind_reports_saved_settings_when_enqueue_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSettingsService.saved_keys = []
    monkeypatch.setattr(enrichments, "SettingsService", _FakeSettingsService)
    enqueue_after_commit = AsyncMock(return_value=None)
    monkeypatch.setattr(
        enrichments.maxmind_service,
        "enqueue_update_after_commit",
        enqueue_after_commit,
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    response = await enrichments.configure_maxmind(
        http_request=SimpleNamespace(client=None, headers={}),
        request=MaxMindConfigureRequest(
            conf_text="""
                AccountID 1234567
                LicenseKey test-license
                EditionIDs GeoLite2-ASN
            """,
        ),
        current_user=SimpleNamespace(username="admin"),
        db=db,
    )

    assert response.account_id == "1234567"
    assert response.edition_ids == ["GeoLite2-ASN"]
    assert response.settings_saved == 4
    assert response.task_id is None
    assert _FakeSettingsService.saved_keys == [
        "enrichment.maxmind.account_id",
        "enrichment.maxmind.license_key",
        "enrichment.maxmind.edition_ids",
        "enrichment.maxmind.enabled",
    ]
    db.commit.assert_awaited_once_with()
    db.rollback.assert_not_awaited()
    enqueue_after_commit.assert_awaited_once_with(db, reschedule=True)
