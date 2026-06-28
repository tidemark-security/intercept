from __future__ import annotations

from datetime import datetime, timezone

from app.models.models import SOCMetricsWindow
from app.services.metrics_service import MetricsService, _outcome_rate_denominator


def test_outcome_rate_denominator_excludes_duplicate_closures() -> None:
    assert _outcome_rate_denominator(closed=10, duplicates=3) == 7
    assert _outcome_rate_denominator(closed=3, duplicates=3) == 0
    assert _outcome_rate_denominator(closed=2, duplicates=5) == 0


def test_soc_summary_rates_ignore_duplicate_closures() -> None:
    summary = MetricsService()._calculate_soc_summary(
        [
            SOCMetricsWindow(
                time_window=datetime(2026, 5, 24, tzinfo=timezone.utc),
                alerts_closed=6,
                alerts_tp=2,
                alerts_fp=1,
                alerts_bp=1,
                alerts_duplicate=2,
            )
        ]
    )

    assert summary.total_alerts_closed == 6
    assert summary.tp_rate == 0.5
    assert summary.fp_rate == 0.25
    assert summary.bp_rate == 0.25
