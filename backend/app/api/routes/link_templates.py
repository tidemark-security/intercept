import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
import logging

from app.core.database import get_db
from app.models.models import (
    LinkTemplate,
    LinkTemplateCreate,
    LinkTemplateRead,
    LinkTemplateResolveRequest,
    LinkTemplateUpdate,
    ResolvedLinkTemplateRead,
    UserAccount,
    UserLinkTemplatePreference,
    UserLinkTemplatePreferenceRead,
    UserLinkTemplatePreferenceUpdate,
)
from app.api.routes.admin_auth import require_authenticated_user, require_admin_user

logger = logging.getLogger(__name__)
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")

router = APIRouter(
    prefix="/link-templates",
    tags=["link-templates"],
    dependencies=[Depends(require_authenticated_user)]
)


def _get_path_value(source: dict, path: str):
    value = source
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
        if value is None:
            return None
    return value


def _lookup_placeholder(path: str, item: dict, user_values: dict):
    if path.startswith("user."):
        return _get_path_value(user_values, path.removeprefix("user."))
    return _get_path_value(item, path)


def _interpolate(template: str, item: dict, user_values: dict, *, encode_values: bool) -> str | None:
    def replace(match: re.Match[str]) -> str:
        value = _lookup_placeholder(match.group(1), item, user_values)
        if value is None:
            raise KeyError(match.group(1))
        rendered = str(value)
        return quote(rendered, safe="") if encode_values else rendered

    try:
        return PLACEHOLDER_PATTERN.sub(replace, template)
    except KeyError:
        return None


def _matches_template(template: LinkTemplate, item: dict) -> bool:
    if template.conditions:
        for field, expected in template.conditions.items():
            if _get_path_value(item, field) != expected:
                return False

    if template.field_names:
        return any(_get_path_value(item, field) is not None for field in template.field_names)

    return True


@router.get("", response_model=List[LinkTemplateRead])
async def get_link_templates(
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all link templates.
    
    Args:
        enabled_only: If True, only return enabled templates (default: True)
        db: Database session
        
    Returns:
        List of link templates ordered by display_order
    """
    try:
        # Build query
        query = select(LinkTemplate).order_by(LinkTemplate.display_order)
        
        if enabled_only:
            query = query.where(LinkTemplate.enabled == True)
        
        # Execute query
        result = await db.execute(query)
        templates = result.scalars().all()
        
        logger.info(f"Retrieved {len(templates)} link templates (enabled_only={enabled_only})")
        return templates
        
    except Exception as e:
        logger.error(f"Error fetching link templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching link templates: {str(e)}"
        )


@router.get("/user-preferences", response_model=List[UserLinkTemplatePreferenceRead])
async def get_user_link_template_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get the authenticated user's link template preferences."""
    result = await db.execute(
        select(UserLinkTemplatePreference)
        .where(UserLinkTemplatePreference.user_id == current_user.id)
        .order_by(UserLinkTemplatePreference.template_id)
    )
    return result.scalars().all()


@router.put("/user-preferences/{template_id}", response_model=UserLinkTemplatePreferenceRead)
async def upsert_user_link_template_preference(
    template_id: int,
    preference_data: UserLinkTemplatePreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Create or update the authenticated user's preference for a link template."""
    template = await db.get(LinkTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Link template {template_id} not found")

    result = await db.execute(
        select(UserLinkTemplatePreference).where(
            UserLinkTemplatePreference.user_id == current_user.id,
            UserLinkTemplatePreference.template_id == template_id,
        )
    )
    preference = result.scalar_one_or_none()

    if preference is None:
        preference = UserLinkTemplatePreference(
            user_id=current_user.id,
            template_id=template_id,
            enabled=preference_data.enabled,
            values=preference_data.values,
        )
        db.add(preference)
    else:
        preference.enabled = preference_data.enabled
        preference.values = preference_data.values
        preference.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(preference)
    return preference


@router.delete("/user-preferences/{template_id}", status_code=204)
async def delete_user_link_template_preference(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Delete the authenticated user's preference for a link template."""
    result = await db.execute(
        select(UserLinkTemplatePreference).where(
            UserLinkTemplatePreference.user_id == current_user.id,
            UserLinkTemplatePreference.template_id == template_id,
        )
    )
    preference = result.scalar_one_or_none()
    if preference is None:
        raise HTTPException(status_code=404, detail=f"Link template preference {template_id} not found")

    await db.delete(preference)
    await db.commit()


@router.post("/resolve", response_model=List[ResolvedLinkTemplateRead])
async def resolve_link_templates(
    request: LinkTemplateResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Resolve enabled global templates using item context and current-user values."""
    templates_result = await db.execute(
        select(LinkTemplate)
        .where(LinkTemplate.enabled == True)
        .order_by(LinkTemplate.display_order)
    )
    preference_result = await db.execute(
        select(UserLinkTemplatePreference).where(
            UserLinkTemplatePreference.user_id == current_user.id,
        )
    )
    preferences = {
        preference.template_id: preference
        for preference in preference_result.scalars().all()
    }

    resolved_links: List[ResolvedLinkTemplateRead] = []
    for template in templates_result.scalars().all():
        preference = preferences.get(template.id)
        if preference is not None and not preference.enabled:
            continue
        if not _matches_template(template, request.item):
            continue

        user_values = preference.values if preference is not None else {}
        url = _interpolate(template.url_template, request.item, user_values, encode_values=True)
        tooltip = _interpolate(template.tooltip_template, request.item, user_values, encode_values=False)
        if not url or tooltip is None:
            continue

        resolved_links.append(
            ResolvedLinkTemplateRead(
                id=template.id,
                template_id=template.template_id,
                name=template.name,
                icon_name=template.icon_name,
                tooltip=tooltip,
                url=url,
                display_order=template.display_order,
            )
        )

    return resolved_links


@router.get("/{template_id}", response_model=LinkTemplateRead)
async def get_link_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific link template by ID.
    
    Args:
        template_id: Database ID of the template
        db: Database session
        
    Returns:
        Link template details
    """
    try:
        result = await db.execute(
            select(LinkTemplate).where(LinkTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Link template {template_id} not found"
            )
        
        return template
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching link template {template_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching link template: {str(e)}"
        )


@router.post("", response_model=LinkTemplateRead)
async def create_link_template(
    template_data: LinkTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_user)
):
    """
    Create a new link template.
    
    Args:
        template_data: Link template data
        db: Database session
        
    Returns:
        Created link template
    """
    try:
        # Check if template_id already exists
        result = await db.execute(
            select(LinkTemplate).where(LinkTemplate.template_id == template_data.template_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Link template with template_id '{template_data.template_id}' already exists"
            )
        
        # Create new template
        template = LinkTemplate(**template_data.model_dump())
        db.add(template)
        await db.commit()
        await db.refresh(template)
        
        logger.info(f"Created link template: {template.template_id} (id={template.id})")
        return template
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating link template: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error creating link template: {str(e)}"
        )


@router.patch("/{template_id}", response_model=LinkTemplateRead)
async def update_link_template(
    template_id: int,
    template_data: LinkTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_user)
):
    """
    Update a link template.
    
    Args:
        template_id: Database ID of the template
        template_data: Updated template data
        db: Database session
        
    Returns:
        Updated link template
    """
    try:
        result = await db.execute(
            select(LinkTemplate).where(LinkTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Link template {template_id} not found"
            )
        
        # Update fields
        update_dict = template_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(template, key, value)
        
        template.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(template)
        
        logger.info(f"Updated link template: {template.template_id} (id={template.id})")
        return template
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating link template {template_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error updating link template: {str(e)}"
        )


@router.delete("/{template_id}")
async def delete_link_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_user)
):
    """
    Delete a link template.
    
    Args:
        template_id: Database ID of the template
        db: Database session
        
    Returns:
        Success message
    """
    try:
        result = await db.execute(
            select(LinkTemplate).where(LinkTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Link template {template_id} not found"
            )
        
        template_info = template.template_id
        await db.delete(template)
        await db.commit()
        
        logger.info(f"Deleted link template: {template_info} (id={template_id})")
        return {"message": f"Link template {template_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting link template {template_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting link template: {str(e)}"
        )
