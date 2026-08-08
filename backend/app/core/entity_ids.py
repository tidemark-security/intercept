"""Canonical entity-ID prefixes and formatting without transport dependencies."""

ALERT_PREFIX = "ALT"
CASE_PREFIX = "CAS"
TASK_PREFIX = "TSK"
RUNBOOK_PREFIX = "RUN"

WORK_ITEM_KIND_TO_PREFIX = {
    "alert": ALERT_PREFIX,
    "case": CASE_PREFIX,
    "task": TASK_PREFIX,
}
KIND_TO_PREFIX = {
    **WORK_ITEM_KIND_TO_PREFIX,
    "runbook": RUNBOOK_PREFIX,
}
PREFIX_TO_KIND = {prefix: kind for kind, prefix in KIND_TO_PREFIX.items()}


def get_prefix_for_kind(kind: str) -> str:
    """Return the canonical prefix for a supported entity kind."""
    try:
        return KIND_TO_PREFIX[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown entity kind: {kind}") from exc


def format_entity_id(numeric_id: int, prefix: str, padding: int = 7) -> str:
    """Format a numeric ID in canonical prefixed form."""
    return f"{prefix}-{numeric_id:0{padding}d}"
