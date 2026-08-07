"""Low-cardinality Prometheus metrics for collector operations."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CollectorCheckpoint, CollectorEvent, CollectorFinding, CollectorRun

_PROVIDER_REQUESTS: Counter[tuple[str, str]] = Counter()
_PROVIDER_REQUEST_DURATION_SUM: defaultdict[str, float] = defaultdict(float)
_PROVIDER_REQUEST_DURATION_COUNT: Counter[str] = Counter()


def record_provider_request(provider_id: str, outcome: str, duration_seconds: float) -> None:
    _PROVIDER_REQUESTS[(provider_id, outcome)] += 1
    _PROVIDER_REQUEST_DURATION_SUM[provider_id] += max(duration_seconds, 0.0)
    _PROVIDER_REQUEST_DURATION_COUNT[provider_id] += 1


def _label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


async def render_collector_metrics(db: AsyncSession) -> list[str]:
    lines = [
        "# HELP collector_runs_total Durable collector runs by outcome",
        "# TYPE collector_runs_total gauge",
    ]
    runs = await db.execute(
        select(CollectorRun.provider_id, CollectorRun.status, CollectorRun.trigger, func.count(CollectorRun.id))
        .group_by(CollectorRun.provider_id, CollectorRun.status, CollectorRun.trigger)
    )
    for provider, status, trigger, count in runs.all():
        lines.append(
            f'collector_runs_total{{provider="{_label(provider)}",status="{_label(status)}",trigger="{_label(trigger)}"}} {count}'
        )

    durations = await db.execute(
        select(
            CollectorRun.provider_id,
            func.count(CollectorRun.id),
            func.sum(func.extract("epoch", CollectorRun.finished_at - CollectorRun.started_at)),
        )
        .where(CollectorRun.started_at.is_not(None), CollectorRun.finished_at.is_not(None))
        .group_by(CollectorRun.provider_id)
    )
    lines.extend(
        [
            "# HELP collector_run_duration_seconds Collector run duration summary",
            "# TYPE collector_run_duration_seconds summary",
        ]
    )
    for provider, count, duration_sum in durations.all():
        label = _label(provider)
        lines.append(f'collector_run_duration_seconds_count{{provider="{label}"}} {count}')
        lines.append(f'collector_run_duration_seconds_sum{{provider="{label}"}} {float(duration_sum or 0):.6f}')

    events = await db.execute(
        select(CollectorEvent.provider_id, CollectorEvent.status, func.count(CollectorEvent.id))
        .group_by(CollectorEvent.provider_id, CollectorEvent.status)
    )
    event_rows = events.all()
    lines.extend(
        [
            "# HELP collector_events_total Durable external events by current outcome",
            "# TYPE collector_events_total gauge",
            "# HELP collector_events_pending Current collector events in non-terminal states",
            "# TYPE collector_events_pending gauge",
        ]
    )
    pending = {"DISCOVERED", "PROCESSING", "AWAITING_VALIDATION", "READY"}
    for provider, state, count in event_rows:
        label = _label(provider)
        state_label = _label(state)
        lines.append(f'collector_events_total{{provider="{label}",outcome="{state_label}"}} {count}')
        if state in pending:
            lines.append(f'collector_events_pending{{provider="{label}",state="{state_label}"}} {count}')

    findings = await db.execute(
        select(
            CollectorEvent.provider_id,
            CollectorFinding.assessment,
            CollectorFinding.status,
            func.count(CollectorFinding.id),
        )
        .join(CollectorEvent, CollectorEvent.id == CollectorFinding.collector_event_id)
        .group_by(CollectorEvent.provider_id, CollectorFinding.assessment, CollectorFinding.status)
    )
    lines.extend(
        [
            "# HELP collector_findings_total Collector findings by assessment and outcome",
            "# TYPE collector_findings_total gauge",
        ]
    )
    for provider, assessment, outcome, count in findings.all():
        lines.append(
            f'collector_findings_total{{provider="{_label(provider)}",assessment="{_label(assessment)}",outcome="{_label(outcome)}"}} {count}'
        )

    lines.extend(
        [
            "# HELP collector_provider_requests_total Provider fetch requests by outcome",
            "# TYPE collector_provider_requests_total counter",
            "# HELP collector_provider_request_duration_seconds Provider fetch duration summary",
            "# TYPE collector_provider_request_duration_seconds summary",
        ]
    )
    for (provider, outcome), count in sorted(_PROVIDER_REQUESTS.items()):
        lines.append(
            f'collector_provider_requests_total{{provider="{_label(provider)}",outcome="{_label(outcome)}"}} {count}'
        )
    for provider, count in sorted(_PROVIDER_REQUEST_DURATION_COUNT.items()):
        label = _label(provider)
        lines.append(f'collector_provider_request_duration_seconds_count{{provider="{label}"}} {count}')
        lines.append(
            f'collector_provider_request_duration_seconds_sum{{provider="{label}"}} {_PROVIDER_REQUEST_DURATION_SUM[provider]:.6f}'
        )

    checkpoints = await db.execute(
        select(CollectorCheckpoint.provider_id, CollectorCheckpoint.stream_key, CollectorCheckpoint.updated_at)
    )
    lines.extend(
        [
            "# HELP collector_checkpoint_age_seconds Age of each durable collector checkpoint",
            "# TYPE collector_checkpoint_age_seconds gauge",
        ]
    )
    now = datetime.now(timezone.utc)
    for provider, stream, updated_at in checkpoints.all():
        lines.append(
            f'collector_checkpoint_age_seconds{{provider="{_label(provider)}",stream="{_label(stream)}"}} {max((now - updated_at).total_seconds(), 0):.3f}'
        )
    lines.append("")
    return lines

