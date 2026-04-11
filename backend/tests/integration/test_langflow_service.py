from __future__ import annotations

import pytest

from app.services.langflow_service import LangFlowService


class _FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


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