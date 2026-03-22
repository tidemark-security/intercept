from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone
import logging

from app.core.database import get_db
from app.models.models import LinkTemplate, LinkTemplateRead, LinkTemplateCreate, LinkTemplateUpdate
from app.api.routes.admin_auth import require_authenticated_user, require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/link-templates",
    tags=["link-templates"],
    dependencies=[Depends(require_authenticated_user)]
)


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
