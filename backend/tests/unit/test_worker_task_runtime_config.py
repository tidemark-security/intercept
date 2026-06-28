from __future__ import annotations

import pytest

from app.core.settings_registry import SETTINGS_REGISTRY, _coerce
from app.services.worker_task_runtime_config import (
    WorkerTaskRuntimeConfig,
    WorkerTaskRuntimeSnapshot,
    load_worker_task_runtime_snapshot,
)


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self.values = values

    async def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)


class EnvAwareStubSettings(StubSettings):
    async def get(self, key: str, default: object = None) -> object:
        import os

        defn = SETTINGS_REGISTRY.get(key)
        if defn is not None:
            raw = os.getenv(defn.env_var)
            if raw is not None:
                return _coerce(raw, defn.value_type)
        return await super().get(key, default)


@pytest.mark.asyncio
async def test_worker_task_runtime_config_defaults_and_inheritance() -> None:
    snapshot = await load_worker_task_runtime_snapshot(StubSettings({}))

    assert snapshot.default_execution_timeout_seconds == 600
    assert snapshot.execution_timeout_for("enrich_item") == 600
    assert snapshot.execution_timeout_for("directory_sync") == 3600
    assert snapshot.retry_timer_for("directory_sync").total_seconds() == 3900


@pytest.mark.asyncio
async def test_worker_task_runtime_config_accepts_per_task_overrides() -> None:
    snapshot = await load_worker_task_runtime_snapshot(
        StubSettings(
            {
                "worker.tasks.default.execution_timeout_seconds": 120,
                "worker.tasks.triage_alert.execution_timeout_seconds": 900,
                "worker.tasks.retry_timer_buffer_seconds": 30,
            }
        )
    )

    assert snapshot.execution_timeout_for("enrich_item") == 120
    assert snapshot.execution_timeout_for("triage_alert") == 900
    assert snapshot.retry_timer_for("triage_alert").total_seconds() == 930


@pytest.mark.asyncio
async def test_worker_task_runtime_config_keeps_last_good_snapshot_on_invalid_value() -> None:
    last_good = WorkerTaskRuntimeSnapshot(default_execution_timeout_seconds=222)
    config = WorkerTaskRuntimeConfig(initial_snapshot=last_good)

    changed = await config.refresh(
        StubSettings({"worker.tasks.default.execution_timeout_seconds": 0})
    )

    assert changed is False
    assert config.snapshot == last_good
    assert config.last_error is not None


@pytest.mark.asyncio
async def test_worker_task_runtime_config_uses_settings_service_env_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKER__TASKS__DEFAULT__EXECUTION_TIMEOUT_SECONDS", "777")

    snapshot = await load_worker_task_runtime_snapshot(EnvAwareStubSettings({}))

    assert snapshot.default_execution_timeout_seconds == 777
