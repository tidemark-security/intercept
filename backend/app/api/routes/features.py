"""
Feature Flags API Routes

Public endpoint for retrieving feature flags without authentication.
Used by frontend to conditionally enable/disable features based on backend configuration.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import logging

from app.core.database import get_db
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/features", tags=["features"])

DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS = [
    "Resolved",
    "False Positive",
    "True Positive",
    "Escalated",
    "No Action Required",
    "Duplicate",
]


def _parse_recommended_tags(setting_value: str | None) -> list[str]:
    if not setting_value:
        return DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS

    parsed_tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in setting_value.split(","):
        normalized_tag = tag.strip()
        if not normalized_tag:
            continue
        lowered_tag = normalized_tag.lower()
        if lowered_tag in seen_tags:
            continue
        seen_tags.add(lowered_tag)
        parsed_tags.append(normalized_tag)

    return parsed_tags or DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS


class FeatureFlags(BaseModel):
    """Public feature flags for frontend."""
    
    ai_triage_enabled: bool = Field(
        default=False,
        description="Whether AI triage is available (LangFlow alert triage flow is configured)"
    )
    ai_triage_auto_enqueue: bool = Field(
        default=True,
        description="Whether to automatically enqueue triage when alerts are created"
    )
    case_closure_recommended_tags: list[str] = Field(
        default_factory=lambda: DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS.copy(),
        description="Recommended case closure tags for the close case modal"
    )


@router.get("", response_model=FeatureFlags)
async def get_feature_flags(
    db: AsyncSession = Depends(get_db),
):
    """
    Get public feature flags.
    
    No authentication required - returns only non-sensitive feature states.
    This endpoint is designed to be called by the frontend to determine
    which features should be displayed.
    """
    settings = SettingsService(db)
    
    # Check if triage flow is configured
    triage_flow_id = await settings.get_typed_value("langflow.alert_triage_flow_id")
    ai_triage_enabled = bool(triage_flow_id)
    
    # Check if auto-enqueue is enabled (defaults to True if not set)
    auto_enqueue = await settings.get_typed_value("triage.auto_enqueue")
    ai_triage_auto_enqueue = auto_enqueue if auto_enqueue is not None else True

    recommended_tags_setting = await settings.get_typed_value("case_closure.recommended_tags")
    case_closure_recommended_tags = _parse_recommended_tags(
        str(recommended_tags_setting) if recommended_tags_setting is not None else None
    )
    
    return FeatureFlags(
        ai_triage_enabled=ai_triage_enabled,
        ai_triage_auto_enqueue=ai_triage_auto_enqueue,
        case_closure_recommended_tags=case_closure_recommended_tags,
    )
