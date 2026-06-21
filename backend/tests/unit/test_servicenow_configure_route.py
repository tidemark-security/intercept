from types import SimpleNamespace

import pytest

from app.api.routes import enrichments
from app.models.models import ServiceNowConfigureRequest


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


@pytest.mark.asyncio
async def test_configure_service_now_uses_registered_servicenow_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSettingsService.values = {}
    FakeSettingsService.created = []
    FakeSettingsService.updated = []
    monkeypatch.setattr(enrichments, "SettingsService", FakeSettingsService)

    response = await enrichments.configure_service_now(
        http_request=SimpleNamespace(client=None, headers={}),
        request=_request(),
        current_user=SimpleNamespace(username="admin"),
        db=None,
    )

    assert response.instance_url == "https://example.service-now.com"
    assert response.settings_saved == 20
    assert response.enabled is True
    assert all(key.startswith("enrichment.servicenow.") for key in FakeSettingsService.created)
    assert "enrichment.servicenow.enabled" in FakeSettingsService.values
    assert "enrichment.servicenow.table" in FakeSettingsService.values
    assert "enrichment.servicenow.user_query_field" in FakeSettingsService.values
    assert "enrichment.servicenow.active_only" in FakeSettingsService.values
    assert "enrichment.service_now.enabled" not in FakeSettingsService.values


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
        db=None,
    )

    assert response.settings_saved == 19
    assert FakeSettingsService.values["enrichment.servicenow.username"] == "svc-user-updated"
    assert FakeSettingsService.values["enrichment.servicenow.password"] == "encrypted-or-decrypted-existing"
    assert FakeSettingsService.values["enrichment.servicenow.oauth_client_secret"] == "existing-oauth-secret"
    assert FakeSettingsService.values["enrichment.servicenow.auth_type"] == "oauth_password"
    assert FakeSettingsService.values["enrichment.servicenow.oauth_client_id"] == "oauth-client"
    assert FakeSettingsService.values["enrichment.servicenow.ttl_seconds"] == "7200"
