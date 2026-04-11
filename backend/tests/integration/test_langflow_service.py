from __future__ import annotations

import pytest

from app.services.langflow_service import LangFlowService


class _FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_list_flows_accepts_array_response(monkeypatch: pytest.MonkeyPatch) -> None:
    service = LangFlowService(base_url="http://example.com/api/v1", api_key="test-key")

    async def fake_get(*args, **kwargs):
        return _FakeResponse(
            200,
            [
                {"id": "uuid-default", "endpoint_name": "tmi_general_purpose", "name": "General"},
                {"id": "uuid-alert", "endpoint_name": "tmi_alert_triage", "name": "Alert"},
            ],
        )

    monkeypatch.setattr(service.client, "get", fake_get)

    try:
        result = await service.list_flows()
    finally:
        await service.close()

    assert result.check_result.success is True
    assert result.check_result.message == "Authenticated LangFlow API returned 2 flows"
    assert result.flows == [
        {"id": "uuid-default", "endpoint_name": "tmi_general_purpose", "name": "General"},
        {"id": "uuid-alert", "endpoint_name": "tmi_alert_triage", "name": "Alert"},
    ]


@pytest.mark.asyncio
async def test_get_mcp_server_treats_json_null_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    service = LangFlowService(base_url="http://example.com/api/v1", api_key="test-key")

    async def fake_get(*args, **kwargs):
        return _FakeResponse(200, None)

    monkeypatch.setattr(service.client, "get", fake_get)

    try:
        result = await service.get_mcp_server("intercept")
    finally:
        await service.close()

    assert result is None


@pytest.mark.asyncio
async def test_upsert_credential_variable_includes_id_on_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService(base_url="http://example.com/api/v1", api_key="test-key")
    captured: dict[str, object] = {}

    async def fake_list_variables():
        return [
            {
                "id": "existing-variable-id",
                "name": "intercept_api_key",
                "type": "Credential",
                "default_fields": [],
            }
        ]

    async def fake_patch(*args, **kwargs):
        captured["url"] = args[0]
        captured["json"] = kwargs.get("json")
        return _FakeResponse(
            200,
            {
                "id": "existing-variable-id",
                "name": "intercept_api_key",
                "type": "Credential",
            },
        )

    monkeypatch.setattr(service, "list_variables", fake_list_variables)
    monkeypatch.setattr(service.client, "patch", fake_patch)

    try:
        result = await service.upsert_credential_variable(
            name="intercept_api_key",
            value="new-secret",
        )
    finally:
        await service.close()

    assert result.action == "updated"
    assert captured["url"] == "http://example.com/api/v1/variables/existing-variable-id"
    assert captured["json"] == {
        "id": "existing-variable-id",
        "name": "intercept_api_key",
        "value": "new-secret",
        "type": "Credential",
        "default_fields": [],
    }