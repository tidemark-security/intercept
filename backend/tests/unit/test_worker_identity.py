import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest

import worker as worker_module
from worker import WorkerHealthServer, _escape_prometheus_label, _resolve_worker_id


def test_worker_id_prefers_explicit_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_ID", "configured-worker")
    monkeypatch.setenv("HOSTNAME", "container-hostname")

    assert _resolve_worker_id() == "configured-worker"


def test_worker_id_falls_back_to_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_ID", raising=False)
    monkeypatch.setenv("HOSTNAME", "container-hostname")

    assert _resolve_worker_id() == "container-hostname"


def test_worker_id_uses_final_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_ID", raising=False)
    monkeypatch.delenv("HOSTNAME", raising=False)

    assert _resolve_worker_id() == "worker-unknown"


def test_prometheus_worker_id_label_is_escaped() -> None:
    assert _escape_prometheus_label('worker\\name\n"quoted"') == (
        'worker\\\\name\\n\\"quoted\\"'
    )


@pytest.mark.asyncio
async def test_readiness_response_does_not_expose_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SimpleNamespace(
        get_worker_readiness=lambda: (False, "database password leaked in exception"),
    )
    monkeypatch.setattr(worker_module, "get_task_queue_service", lambda: service)

    response = await WorkerHealthServer(port=0).ready(cast(Any, None))
    payload = json.loads(response.text)

    assert response.status == 503
    assert payload["reason"] == "worker unavailable"
    assert "database password" not in response.text


@pytest.mark.asyncio
async def test_uninitialized_readiness_has_same_safe_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_service():
        raise RuntimeError("queue has not been initialized")

    monkeypatch.setattr(worker_module, "get_task_queue_service", unavailable_service)

    response = await WorkerHealthServer(port=0).ready(cast(Any, None))
    payload = json.loads(response.text)

    assert response.status == 503
    assert payload["reason"] == "worker unavailable"


@pytest.mark.asyncio
async def test_worker_failure_ends_shutdown_wait() -> None:
    async def fail_worker() -> None:
        await asyncio.sleep(0)
        raise TypeError("worker programming failure")

    worker_task = asyncio.create_task(fail_worker())

    with pytest.raises(TypeError, match="worker programming failure"):
        await worker_module._wait_for_shutdown_or_worker_failure(  # type: ignore[attr-defined]
            asyncio.Event(),
            worker_task,
        )
