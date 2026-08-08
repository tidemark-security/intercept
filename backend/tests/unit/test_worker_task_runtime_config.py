from __future__ import annotations

import pytest

from app.core.settings_registry import SETTINGS_REGISTRY, coerce_setting_value
from app.services.task_names import WORKER_TASK_NAMES
from app.services.worker_task_runtime_config import (
    KNOWN_WORKER_TASK_NAMES,
    WorkerTaskRuntimeConfig,
    WorkerTaskRuntimeSnapshot,
    load_worker_task_runtime_snapshot,
)


def test_runtime_config_uses_canonical_worker_task_names() -> None:
    assert KNOWN_WORKER_TASK_NAMES is WORKER_TASK_NAMES


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
                return coerce_setting_value(raw, defn.value_type)
        return await super().get(key, default)


class FailingSettings:
    def __init__(self, error: Exception):
        self.error = error

    async def get(self, key: str, default: object = None) -> object:
        raise self.error


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
async def test_worker_task_runtime_config_keeps_last_good_snapshot_when_database_is_unavailable() -> None:
    last_good = WorkerTaskRuntimeSnapshot(default_execution_timeout_seconds=222)
    config = WorkerTaskRuntimeConfig(initial_snapshot=last_good)

    changed = await config.refresh(FailingSettings(ConnectionError("database unavailable")))

    assert changed is False
    assert config.snapshot == last_good
    assert config.last_error is not None


@pytest.mark.asyncio
async def test_worker_task_runtime_config_does_not_hide_programming_errors() -> None:
    config = WorkerTaskRuntimeConfig()

    with pytest.raises(TypeError, match="settings integration bug"):
        await config.refresh(FailingSettings(TypeError("settings integration bug")))


@pytest.mark.asyncio
async def test_worker_task_runtime_config_uses_settings_service_env_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKER__TASKS__DEFAULT__EXECUTION_TIMEOUT_SECONDS", "777")

    snapshot = await load_worker_task_runtime_snapshot(EnvAwareStubSettings({}))

    assert snapshot.default_execution_timeout_seconds == 777
