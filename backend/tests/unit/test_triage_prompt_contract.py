from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_string_values(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_string_values(item))
        return strings
    return []


def _triage_prompt() -> str:
    asset_path = Path(__file__).resolve().parents[2] / "app/static/langflow/tmi_alert_triage.json"
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    for value in _string_values(asset):
        if "# Tidemark Intercept" in value and "Alert Triage Agent" in value:
            return value
    raise AssertionError("Alert triage prompt not found in LangFlow asset")


def test_triage_prompt_contains_canonical_case_path_contract() -> None:
    prompt = _triage_prompt()

    assert "Disposition-to-case-path mapping" in prompt
    assert "TRUE_POSITIVE -> request_escalate_to_case=true -> suggested_status=ESCALATED" in prompt
    assert "FALSE_POSITIVE -> request_escalate_to_case=false -> suggested_status=CLOSED_FP" in prompt
    assert "BENIGN -> request_escalate_to_case=false -> suggested_status=CLOSED_BP" in prompt
    assert "NEEDS_INVESTIGATION -> request_escalate_to_case=true -> suggested_status=ESCALATED" in prompt
    assert "DUPLICATE -> request_escalate_to_case=false -> suggested_status=CLOSED_DUPLICATE" in prompt
    assert "UNKNOWN -> request_escalate_to_case=true -> suggested_status=ESCALATED" in prompt


def test_triage_prompt_limits_recommended_actions_to_escalations() -> None:
    prompt = _triage_prompt()

    assert "recommended_actions are required only for escalating dispositions" in prompt
    assert "For dismissal dispositions, omit recommended_actions or send []" in prompt
    assert "evidence_refs" not in prompt
    assert "* `recommended_actions` (3-7 action objects" not in prompt


def test_triage_prompt_requires_human_curated_context_awareness() -> None:
    prompt = _triage_prompt()

    assert "context" in prompt
    assert "human-curated" in prompt
    assert "MUST consider" in prompt


def test_triage_prompt_explains_case_runbook_discovery_tools() -> None:
    prompt = _triage_prompt()

    assert "search_case_runbooks" in prompt
    assert "get_case_runbook" in prompt
    assert "recommended_case_runbook_id" in prompt
    assert "recommended_case_runbook_id and recommended_actions are mutually exclusive" in prompt
