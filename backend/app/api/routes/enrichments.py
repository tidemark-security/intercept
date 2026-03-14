from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user, require_authenticated_user
from app.core.database import get_db
from app.models.models import (
    EnrichmentAliasCreate,
    EnrichmentAliasRead,
    EnrichmentAliasUpdate,
    EnrichmentProviderStatusRead,
)
from app.services.enrichment.registry import enrichment_registry
from app.services.enrichment.service import enrichment_service


router = APIRouter(
    prefix="/enrichments",
    tags=["enrichments"],
    dependencies=[Depends(require_authenticated_user)],
)

admin_router = APIRouter(
    prefix="/admin/enrichments",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


@router.get("/aliases/search", response_model=List[EnrichmentAliasRead])
async def search_aliases(
    q: str = Query(..., min_length=1, description="Alias search query"),
    entity_type: str = Query(..., description="Canonical entity type, such as user or ip"),
    provider_id: Optional[str] = Query(None, description="Optional provider filter"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await enrichment_service.search_aliases(
        db,
        query=q,
        entity_type=entity_type,
        provider_id=provider_id,
        limit=limit,
    )


@router.post("/{entity_type}/{entity_id}/items/{item_id}/enqueue")
async def enqueue_item_enrichment(
    entity_type: str,
    entity_id: int,
    item_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        task_id = await enrichment_service.enqueue_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        await db.commit()
        return {"enqueued": True, "task_id": task_id}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@admin_router.get("/providers", response_model=List[EnrichmentProviderStatusRead])
async def get_provider_statuses(db: AsyncSession = Depends(get_db)):
    return await enrichment_service.get_provider_statuses(db)


@admin_router.post("/providers/{provider_id}/directory-sync")
async def enqueue_directory_sync(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
):
    if enrichment_registry.get(provider_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    try:
        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_DIRECTORY_SYNC

        task_id = await get_task_queue_service().enqueue(
            task_name=TASK_DIRECTORY_SYNC,
            payload={"provider_id": provider_id},
        )
        return {"enqueued": True, "task_id": task_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@admin_router.post("/aliases", response_model=EnrichmentAliasRead, status_code=status.HTTP_201_CREATED)
async def create_alias(
    alias: EnrichmentAliasCreate,
    db: AsyncSession = Depends(get_db),
):
    return await enrichment_service.upsert_alias(db, alias)


@admin_router.put("/aliases/{alias_id}", response_model=EnrichmentAliasRead)
async def update_alias(
    alias_id: int,
    alias_update: EnrichmentAliasUpdate,
    db: AsyncSession = Depends(get_db),
):
    updated = await enrichment_service.update_alias(db, alias_id, alias_update)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found")
    return updated


@admin_router.delete("/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alias(
    alias_id: int,
    db: AsyncSession = Depends(get_db),
):
    deleted = await enrichment_service.delete_alias(db, alias_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found")
    return None


@admin_router.post("/cache/clear")
async def clear_cache(
    provider_id: Optional[str] = Query(None, description="Optional provider identifier to clear"),
    db: AsyncSession = Depends(get_db),
):
    cleared = await enrichment_service.clear_cache(db, provider_id)
    return {"cleared": cleared, "provider_id": provider_id}