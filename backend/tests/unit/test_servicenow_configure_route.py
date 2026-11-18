from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import enrichments
from app.models.models import ServiceNowConfigureRequest, ServiceNowPreviewRequest


class FakeSettingsService:
    values: dict[str, str] = {}
    created: list[str] = []
    updated: list[str] = []

    def __init__(self, _db):
        pass

    async def get_setting(self, key: str, include_secret: bool = False):
        if key not in self.values:
            return None
        return SimpleNamespace(id=1, key=key, value=self.values[key])

    async def create_setting(self, setting_create, **_kwargs):
        self.created.append(setting_create.key)
        self.values[setting_create.key] = setting_create.value
        return SimpleNamespace(id=1, key=setting_create.key, value=setting_create.value)

    async def update_setting(self, key: str, setting_update, **_kwargs):
        self.updated.append(key)
        self.values[key] = setting_update.value
        return SimpleNamespace(id=1, key=key, value=setting_update.value)

    async def upsert_setting_in_transaction(self, setting_create, **_kwargs):
        key = setting_create.key
        if key in self.values:
            self.updated.append(key)
        else:
            self.created.append(key)
        self.values[key] = setting_create.value
        return SimpleNamespace(id=1, key=key, value=setting_create.value)


def _request(**overrides):
    data = {
        "instance_url": "https://example.service-now.com/",
        "username": "svc-user",
        "password": "svc-pass",
        "user_query_field": "email",
        "ttl_seconds": 3600,
        "enabled": True,
    }
    data.update(overrides)
    return ServiceNowConfigureRequest(**data)


def _preview_request(**overrides):
    data = _request().model_dump()
    data["item"] = {"type": "internal_actor", "contact_email": "alice@example.com"}
    data.update(overrides)
    return ServiceNowPreviewRequest(**data)


@pytest.mark.asyncio
async def test_configure_service_now_uses_registered_servicenow_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSettingsService.values = {}
    FakeSettingsService.created = []
    FakeSettingsService.updated = []
    monkeypatch.setattr(enrichments, "SettingsService", FakeSettingsService)
    enqueue_refresh = AsyncMock()
    monkeypatch.setattr(enrichments, "enqueue_bulk_sync_schedule_refresh", enqueue_refresh)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    response = await enrichments.configure_service_now(
        http_request=SimpleNamespace(client=None, headers={}),
        request=_request(),
        current_user=SimpleNamespace(username="admin"),
        db=db,
    )

    assert response.instance_url == "https://example.service-now.com"
    assert response.settings_saved == 22
    assert response.enabled is True
    assert all(key.startswith("enrichment.servicenow.") for key in FakeSettingsService.created)
    assert "enrichment.servicenow.enabled" in FakeSettingsService.values
    assert "enrichment.servicenow.table" in FakeSettingsService.values
    assert FakeSettingsService.values["enrichment.servicenow.user_table_enabled"] == "true"
    assert "enrichment.servicenow.user_query_field" in FakeSettingsService.values
    assert FakeSettingsService.values["enrichment.servicenow.cmdb_table_enabled"] == "true"
    assert "enrichment.servicenow.active_only" in FakeSettingsService.values
    assert "enrichment.service_now.enabled" not in FakeSettingsService.values
    db.commit.assert_awaited_once_with()
    db.rollback.assert_not_awaited()
    enqueue_refresh.assert_awaited_once_with("servicenow")


@pytest.mark.asyncio
async def test_configure_service_now_preserves_blank_saved_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSettingsService.values = {
        "enrichment.servicenow.instance_url": "https://example.service-now.com",
        "enrichment.servicenow.username": "svc-user",
        "enrichment.servicenow.password": "encrypted-or-decrypted-existing",
        "enrichment.servicenow.oauth_client_secret": "existing-oauth-secret",
    }
    FakeSettingsService.created = []
    FakeSettingsService.updated = []
    monkeypatch.setattr(enrichments, "SettingsService", FakeSettingsService)
    enqueue_refresh = AsyncMock()
    monkeypatch.setattr(enrichments, "enqueue_bulk_sync_schedule_refresh", enqueue_refresh)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    response = await enrichments.configure_service_now(
        http_request=SimpleNamespace(client=None, headers={}),
        request=_request(
            username="svc-user-updated",
            password="",
            auth_type="oauth_password",
            oauth_client_id="oauth-client",
            oauth_client_secret="",
            ttl_seconds=7200,
        ),
        current_user=SimpleNamespace(username="admin"),
        db=db,
    )

    assert response.settings_saved == 21
    assert FakeSettingsService.values["enrichment.servicenow.username"] == "svc-user-updated"
    assert FakeSettingsService.values["enrichment.servicenow.password"] == "encrypted-or-decrypted-existing"
    assert FakeSettingsService.values["enrichment.servicenow.oauth_client_secret"] == "existing-oauth-secret"
    assert FakeSettingsService.values["enrichment.servicenow.auth_type"] == "oauth_password"
    assert FakeSettingsService.values["enrichment.servicenow.oauth_client_id"] == "oauth-client"
    assert FakeSettingsService.values["enrichment.servicenow.ttl_seconds"] == "7200"
    db.commit.assert_awaited_once_with()
    enqueue_refresh.assert_awaited_once_with("servicenow")


@pytest.mark.asyncio
async def test_preview_service_now_uses_saved_secret_when_request_secret_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSettingsService.values = {
        "enrichment.servicenow.password": "saved-service-now-password",
        "enrichment.servicenow.oauth_client_secret": "saved-oauth-secret",
    }
    FakeSettingsService.created = []
    FakeSettingsService.updated = []
    captured: dict[str, object] = {}

    class FakeServiceNowProvider:
        async def preview(self, *, config, item):
            captured["config"] = config
            captured["item"] = item
            return SimpleNamespace(
                provider_id="servicenow",
                cache_key="user:alice@example.com",
                enrichment_data={},
                aliases=[],
            )

    monkeypatch.setattr(enrichments, "SettingsService", FakeSettingsService)
    monkeypatch.setattr(enrichments, "servicenow_provider", FakeServiceNowProvider())

    response = await enrichments.preview_service_now(
        request=_preview_request(password="", oauth_client_secret=""),
        db=None,
    )

    assert response.provider_id == "servicenow"
    assert captured["config"]["password"] == "saved-service-now-password"
    assert captured["config"]["oauth_client_secret"] == "saved-oauth-secret"
    assert captured["item"] == {
        "type": "internal_actor",
        "contact_email": "alice@example.com",
    }
