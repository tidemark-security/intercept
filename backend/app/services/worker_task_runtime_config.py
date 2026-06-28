"""Runtime-configurable worker task timeout settings."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType
from typing import Any, Mapping

logger = logging.getLogger(__name__)


KNOWN_WORKER_TASK_NAMES = (
    "langflow_chat",
    "langflow_batch",
    "triage_alert",
    "autonomous_task",
    "enrich_item",
    "directory_sync",
    "refresh_bulk_sync_schedules",
    "maxmind_update",
)

DEFAULT_EXECUTION_TIMEOUT_SECONDS = 600.0
DEFAULT_DIRECTORY_SYNC_TIMEOUT_SECONDS = 3600.0
DEFAULT_RETRY_INITIAL_DELAY_SECONDS = 5.0
DEFAULT_RETRY_MAX_DELAY_SECONDS = 60.0
DEFAULT_RETRY_TIMER_BUFFER_SECONDS = 300.0
DEFAULT_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS = 30.0

MIN_EXECUTION_TIMEOUT_SECONDS = 1.0
MAX_EXECUTION_TIMEOUT_SECONDS = 86_400.0
MIN_RETRY_DELAY_SECONDS = 0.1
MAX_RETRY_DELAY_SECONDS = 3_600.0
MIN_RETRY_TIMER_BUFFER_SECONDS = 1.0
MAX_RETRY_TIMER_BUFFER_SECONDS = 86_400.0
MIN_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS = 1.0
MAX_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS = 3_600.0


@dataclass(frozen=True)
class WorkerTaskRuntimeSnapshot:
    """Immutable worker task runtime settings used for one task attempt."""

    default_execution_timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS
    task_execution_timeout_seconds: Mapping[str, float] = field(
        default_factory=lambda: {"directory_sync": DEFAULT_DIRECTORY_SYNC_TIMEOUT_SECONDS}
    )
    retry_initial_delay_seconds: float = DEFAULT_RETRY_INITIAL_DELAY_SECONDS
    retry_max_delay_seconds: float = DEFAULT_RETRY_MAX_DELAY_SECONDS
    retry_timer_buffer_seconds: float = DEFAULT_RETRY_TIMER_BUFFER_SECONDS
    refresh_interval_seconds: float = DEFAULT_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "task_execution_timeout_seconds",
            MappingProxyType(dict(self.task_execution_timeout_seconds)),
        )

    def execution_timeout_for(self, task_name: str) -> float:
        return float(
            self.task_execution_timeout_seconds.get(
                task_name,
                self.default_execution_timeout_seconds,
            )
        )

    def retry_timer_for(self, task_name: str) -> timedelta:
        return timedelta(
            seconds=self.execution_timeout_for(task_name) + self.retry_timer_buffer_seconds
        )


DEFAULT_WORKER_TASK_RUNTIME_SNAPSHOT = WorkerTaskRuntimeSnapshot()


class WorkerTaskRuntimeConfig:
    """Holds the last valid worker task runtime snapshot."""

    def __init__(
        self,
        initial_snapshot: WorkerTaskRuntimeSnapshot = DEFAULT_WORKER_TASK_RUNTIME_SNAPSHOT,
    ) -> None:
        self._snapshot = initial_snapshot
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def snapshot(self) -> WorkerTaskRuntimeSnapshot:
        return self._snapshot

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def refresh(self, settings: Any) -> bool:
        """Load a new snapshot, keeping the previous one if validation fails."""
        async with self._lock:
            try:
                next_snapshot = await load_worker_task_runtime_snapshot(settings)
            except Exception as exc:
                self._last_error = str(exc) or exc.__class__.__name__
                logger.warning(
                    "Keeping previous worker task runtime config after refresh failure: %s",
                    self._last_error,
                )
                return False

            changed = next_snapshot != self._snapshot
            self._snapshot = next_snapshot
            self._last_error = None
            return changed


async def load_worker_task_runtime_snapshot(settings: Any) -> WorkerTaskRuntimeSnapshot:
    """Read and validate worker task runtime settings from SettingsService-like API."""
    default_timeout = await _number_setting(
        settings,
        "worker.tasks.default.execution_timeout_seconds",
        DEFAULT_EXECUTION_TIMEOUT_SECONDS,
        minimum=MIN_EXECUTION_TIMEOUT_SECONDS,
        maximum=MAX_EXECUTION_TIMEOUT_SECONDS,
    )

    task_timeouts: dict[str, float] = {}
    for task_name in KNOWN_WORKER_TASK_NAMES:
        setting_key = f"worker.tasks.{task_name}.execution_timeout_seconds"
        default = (
            DEFAULT_DIRECTORY_SYNC_TIMEOUT_SECONDS
            if task_name == "directory_sync"
            else None
        )
        timeout = await _optional_number_setting(
            settings,
            setting_key,
            default=default,
            minimum=MIN_EXECUTION_TIMEOUT_SECONDS,
            maximum=MAX_EXECUTION_TIMEOUT_SECONDS,
        )
        if timeout is not None:
            task_timeouts[task_name] = timeout

    retry_initial_delay = await _number_setting(
        settings,
        "worker.tasks.retry_initial_delay_seconds",
        DEFAULT_RETRY_INITIAL_DELAY_SECONDS,
        minimum=MIN_RETRY_DELAY_SECONDS,
        maximum=MAX_RETRY_DELAY_SECONDS,
    )
    retry_max_delay = await _number_setting(
        settings,
        "worker.tasks.retry_max_delay_seconds",
        DEFAULT_RETRY_MAX_DELAY_SECONDS,
        minimum=MIN_RETRY_DELAY_SECONDS,
        maximum=MAX_RETRY_DELAY_SECONDS,
    )
    if retry_max_delay < retry_initial_delay:
        raise ValueError(
            "worker.tasks.retry_max_delay_seconds must be greater than or equal "
            "to worker.tasks.retry_initial_delay_seconds"
        )

    retry_timer_buffer = await _number_setting(
        settings,
        "worker.tasks.retry_timer_buffer_seconds",
        DEFAULT_RETRY_TIMER_BUFFER_SECONDS,
        minimum=MIN_RETRY_TIMER_BUFFER_SECONDS,
        maximum=MAX_RETRY_TIMER_BUFFER_SECONDS,
    )
    refresh_interval = await _number_setting(
        settings,
        "worker.task_settings_refresh_interval_seconds",
        DEFAULT_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS,
        minimum=MIN_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS,
        maximum=MAX_TASK_SETTINGS_REFRESH_INTERVAL_SECONDS,
    )

    return WorkerTaskRuntimeSnapshot(
        default_execution_timeout_seconds=default_timeout,
        task_execution_timeout_seconds=task_timeouts,
        retry_initial_delay_seconds=retry_initial_delay,
        retry_max_delay_seconds=retry_max_delay,
        retry_timer_buffer_seconds=retry_timer_buffer,
        refresh_interval_seconds=refresh_interval,
    )


async def _number_setting(
    settings: Any,
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = await settings.get(key, default)
    return _validate_number(key, value, minimum=minimum, maximum=maximum)


async def _optional_number_setting(
    settings: Any,
    key: str,
    *,
    default: float | None,
    minimum: float,
    maximum: float,
) -> float | None:
    value = await settings.get(key, default)
    if value is None:
        return None
    return _validate_number(key, value, minimum=minimum, maximum=maximum)


def _validate_number(key: str, value: Any, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number")

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc

    if number < minimum or number > maximum:
        raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}")

    return number
