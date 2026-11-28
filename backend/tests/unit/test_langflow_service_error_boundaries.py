from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.langflow_service import LangFlowError, LangFlowService


class _StreamingResponse:
    def __init__(
        self,
        lines: list[str],
        *,
        status_code: int = 200,
    ) -> None:
        self._lines = lines
        self.status_code = status_code

    async def __aenter__(self) -> "_StreamingResponse":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return

        request = httpx.Request("POST", "http://langflow.test/run/flow")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError(
            "stream failed",
            request=request,
            response=response,
        )

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line


async def _collect_stream(service: LangFlowService) -> list[dict[str, object]]:
    return [
        event
        async for event in service.stream_message(
            flow_id="flow",
            message="hello",
        )
    ]


@pytest.mark.asyncio
async def test_send_message_propagates_unexpected_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "post",
        AsyncMock(side_effect=RuntimeError("programming defect")),
    )

    try:
        with pytest.raises(RuntimeError, match="programming defect"):
            await service.send_message("flow", "hello")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_send_message_rejects_invalid_json_without_logging_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_body = "secret malformed response body"
    response = httpx.Response(
        200,
        content=secret_body,
        request=httpx.Request("POST", "http://langflow.test/run/flow"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "post", AsyncMock(return_value=response))

    try:
        with pytest.raises(
            LangFlowError,
            match="LangFlow API returned an invalid JSON response",
        ):
            await service.send_message("flow", "hello")
    finally:
        await service.close()

    assert secret_body not in caplog.text


@pytest.mark.asyncio
async def test_send_message_http_error_does_not_log_response_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_body = "secret upstream diagnostic"
    response = httpx.Response(
        502,
        content=secret_body,
        request=httpx.Request("POST", "http://langflow.test/run/flow"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "post", AsyncMock(return_value=response))

    try:
        with pytest.raises(LangFlowError, match="LangFlow API returned error 502"):
            await service.send_message("flow", "hello")
    finally:
        await service.close()

    assert secret_body not in caplog.text


@pytest.mark.asyncio
async def test_send_message_rejects_non_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(
        200,
        json=["not", "an", "object"],
        request=httpx.Request("POST", "http://langflow.test/run/flow"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "post", AsyncMock(return_value=response))

    try:
        with pytest.raises(
            LangFlowError,
            match="LangFlow API returned an unexpected response body",
        ):
            await service.send_message("flow", "hello")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_run_flow_streaming_propagates_unexpected_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")

    def fail_stream(*_args: object, **_kwargs: object) -> _StreamingResponse:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(service.client, "stream", fail_stream)

    try:
        with pytest.raises(RuntimeError, match="programming defect"):
            await service.run_flow_streaming("flow", "hello")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_run_flow_streaming_does_not_log_malformed_or_error_event_content(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_malformed_line = "secret malformed SSE content"
    secret_error_detail = "secret upstream stack trace"
    response = _StreamingResponse(
        [
            secret_malformed_line,
            f'{{"event":"error","data":{{"detail":"{secret_error_detail}"}}}}',
        ]
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "stream", lambda *_args, **_kwargs: response)

    try:
        with pytest.raises(
            LangFlowError,
            match="^LangFlow flow emitted an error event$",
        ):
            await service.run_flow_streaming("flow", "hello")
    finally:
        await service.close()

    assert secret_malformed_line not in caplog.text
    assert secret_error_detail not in caplog.text


@pytest.mark.asyncio
async def test_run_flow_streaming_rejects_non_object_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "stream",
        lambda *_args, **_kwargs: _StreamingResponse(['["unexpected"]']),
    )

    try:
        with pytest.raises(
            LangFlowError,
            match="LangFlow stream returned an unexpected event body",
        ):
            await service.run_flow_streaming("flow", "hello")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_stream_message_propagates_unexpected_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")

    def fail_stream(*_args: object, **_kwargs: object) -> _StreamingResponse:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(service.client, "stream", fail_stream)

    try:
        with pytest.raises(RuntimeError, match="programming defect"):
            await _collect_stream(service)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_stream_message_skips_malformed_content_without_logging_it(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_line = "data: secret malformed chat content"
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "stream",
        lambda *_args, **_kwargs: _StreamingResponse(
            [secret_line, 'data: {"event":"token","data":{"chunk":"ok"}}']
        ),
    )

    try:
        events = await _collect_stream(service)
    finally:
        await service.close()

    assert events == [{"event": "token", "data": {"chunk": "ok"}}]
    assert secret_line not in caplog.text


@pytest.mark.asyncio
async def test_stream_message_rejects_non_object_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "stream",
        lambda *_args, **_kwargs: _StreamingResponse(["data: [1, 2, 3]"]),
    )

    try:
        with pytest.raises(
            LangFlowError,
            match="LangFlow stream returned an unexpected event body",
        ):
            await _collect_stream(service)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_connectivity_check_propagates_unexpected_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "get",
        AsyncMock(side_effect=RuntimeError("programming defect")),
    )

    try:
        with pytest.raises(RuntimeError, match="programming defect"):
            await service.run_connectivity_check()
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_connectivity_check_handles_malformed_json_without_logging_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_body = "secret malformed health response"
    response = httpx.Response(
        200,
        content=secret_body,
        request=httpx.Request("GET", "http://langflow.test/health"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "get", AsyncMock(return_value=response))

    try:
        result = await service.run_connectivity_check()
    finally:
        await service.close()

    assert result.success is False
    assert result.message == "LangFlow health endpoint returned an unexpected response body"
    assert secret_body not in caplog.text


@pytest.mark.asyncio
async def test_connectivity_check_rejects_non_object_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(
        200,
        json=[{"status": "ok"}],
        request=httpx.Request("GET", "http://langflow.test/health"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "get", AsyncMock(return_value=response))

    try:
        result = await service.run_connectivity_check()
    finally:
        await service.close()

    assert result.success is False
    assert result.message == "LangFlow health endpoint returned an unexpected response body"


@pytest.mark.asyncio
async def test_list_flows_propagates_unexpected_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(
        service.client,
        "get",
        AsyncMock(side_effect=RuntimeError("programming defect")),
    )

    try:
        with pytest.raises(RuntimeError, match="programming defect"):
            await service.list_flows()
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_list_flows_handles_malformed_json_without_logging_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_body = "secret malformed flow response"
    response = httpx.Response(
        200,
        content=secret_body,
        request=httpx.Request("GET", "http://langflow.test/api/v1/flows/"),
    )
    service = LangFlowService("http://langflow.test/api/v1", api_key="key")
    monkeypatch.setattr(service.client, "get", AsyncMock(return_value=response))

    try:
        result = await service.list_flows()
    finally:
        await service.close()

    assert result.check_result.success is False
    assert (
        result.check_result.message
        == "LangFlow flow listing returned an unexpected response body"
    )
    assert secret_body not in caplog.text
