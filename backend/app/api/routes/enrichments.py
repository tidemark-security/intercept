from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

import httpx
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user, require_authenticated_user, require_non_auditor_user
from app.core.database import get_db
from app.models.enums import SettingType
from app.models.models import (
    AppSettingCreate,
    AppSettingUpdate,
    EnrichmentAliasCreate,
    EnrichmentAliasRead,
    EnrichmentAliasUpdate,
    EnrichmentProviderStatusRead,
    MaxMindConfigureRequest,
    MaxMindConfigureResponse,
    MaxMindDatabaseStatus,
    ServiceNowConfigureRequest,
    ServiceNowConfigureResponse,
    ServiceNowPreviewRequest,
    ServiceNowPreviewResponse,
    UserAccount,
)
from app.services.audit_service import AuditContext
from app.services.enrichment.providers.servicenow import servicenow_provider
from app.services.enrichment.registry import enrichment_registry
from app.services.enrichment.service import enrichment_service
from app.services.maxmind_service import maxmind_service
from app.services.settings_service import SettingsService


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
    _current_user: UserAccount = Depends(require_non_auditor_user),
):
    try:
        task_id = await enrichment_service.enqueue_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
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
    provider = enrichment_registry.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if not provider.supports_bulk_sync:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider does not support bulk sync")

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


async def _upsert_setting(
    settings_service: SettingsService,
    *,
    key: str,
    value: str,
    is_secret: bool = False,
    value_type: SettingType = SettingType.STRING,
    performed_by: Optional[str] = None,
    audit_context: Optional[AuditContext] = None,
) -> None:
    existing = await settings_service.get_setting(key, include_secret=True)
    if existing is not None and existing.id > 0:
        await settings_service.update_setting(
            key,
            AppSettingUpdate(value=value),
            performed_by=performed_by,
            audit_context=audit_context,
        )
        return

    await settings_service.create_setting(
        AppSettingCreate(
            key=key,
            value=value,
            value_type=value_type,
            is_secret=is_secret,
            category="enrichment",
            description="",
        ),
        performed_by=performed_by,
        audit_context=audit_context,
    )


@admin_router.post("/maxmind/configure", response_model=MaxMindConfigureResponse)
async def configure_maxmind(
    http_request: Request,
    request: MaxMindConfigureRequest,
    current_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed = maxmind_service.parse_geoip_conf(request.conf_text)
        settings_service = SettingsService(db)  # type: ignore[arg-type]
        audit_context = AuditContext(
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
            correlation_id=http_request.headers.get("x-correlation-id"),
        )

        await _upsert_setting(
            settings_service,
            key="enrichment.maxmind.account_id",
            value=parsed["account_id"],
            performed_by=current_user.username,
            audit_context=audit_context,
        )
        await _upsert_setting(
            settings_service,
            key="enrichment.maxmind.license_key",
            value=parsed["license_key"],
            is_secret=True,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
        await _upsert_setting(
            settings_service,
            key="enrichment.maxmind.edition_ids",
            value=maxmind_service.serialize_edition_ids(parsed["edition_ids"]),
            value_type=SettingType.JSON,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
        await _upsert_setting(
            settings_service,
            key="enrichment.maxmind.enabled",
            value="true",
            value_type=SettingType.BOOLEAN,
            performed_by=current_user.username,
            audit_context=audit_context,
        )

        task_id = await maxmind_service.enqueue_update(db, reschedule=True)
        return MaxMindConfigureResponse(
            account_id=parsed["account_id"],
            edition_ids=parsed["edition_ids"],
            settings_saved=4,
            task_id=task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@admin_router.get("/maxmind/databases", response_model=List[MaxMindDatabaseStatus])
async def get_maxmind_database_status(db: AsyncSession = Depends(get_db)):
    statuses = await maxmind_service.get_database_status(db)
    return [MaxMindDatabaseStatus.model_validate(status_row) for status_row in statuses]


@admin_router.post("/maxmind/update")
async def trigger_maxmind_update(db: AsyncSession = Depends(get_db)):
    try:
        task_id = await maxmind_service.enqueue_update(db, reschedule=False)
        return {"enqueued": True, "task_id": task_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@admin_router.post("/service-now/configure", response_model=ServiceNowConfigureResponse)
async def configure_service_now(
    http_request: Request,
    request: ServiceNowConfigureRequest,
    current_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        settings_service = SettingsService(db)  # type: ignore[arg-type]
        request_data = request.model_dump()
        for key_suffix in ("password", "oauth_client_secret"):
            if request_data.get(key_suffix):
                continue
            existing = await settings_service.get_setting(
                f"enrichment.servicenow.{key_suffix}",
                include_secret=True,
            )
            if existing and existing.value:
                request_data[key_suffix] = existing.value

        normalized = servicenow_provider.normalize_config(request_data)
        audit_context = AuditContext(
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
            correlation_id=http_request.headers.get("x-correlation-id"),
        )

        setting_values = {
            "instance_url": normalized["instance_url"],
            "username": normalized["username"],
            "auth_type": normalized["auth_type"],
            "oauth_client_id": normalized["oauth_client_id"],
            "table": normalized["table"],
            "user_query_field": request.user_query_field.strip(),
            "active_only": "true" if request.active_only else "false",
            "fields": normalized["fields"],
            "lookup_query_template": normalized["lookup_query_template"],
            "bulk_sync_query": normalized["bulk_sync_query"],
            "user_vip_field": normalized["user_vip_field"],
            "user_privileged_field": normalized["user_privileged_field"],
            "cmdb_table": normalized["cmdb_table"],
            "cmdb_query_field": normalized["cmdb_query_field"],
            "cmdb_fields": normalized["cmdb_fields"],
            "cmdb_criticality_field": normalized["cmdb_criticality_field"],
            "cmdb_privileged_field": normalized["cmdb_privileged_field"],
            "ttl_seconds": str(request.ttl_seconds),
            "enabled": "true" if request.enabled else "false",
        }
        if request.password:
            setting_values["password"] = normalized["password"]
        if request.oauth_client_secret:
            setting_values["oauth_client_secret"] = normalized["oauth_client_secret"]
        boolean_keys = {"enabled", "active_only"}
        number_keys = {"ttl_seconds"}
        secret_keys = {"password", "oauth_client_secret"}

        for key_suffix, value in setting_values.items():
            await _upsert_setting(
                settings_service,
                key=f"enrichment.servicenow.{key_suffix}",
                value=value,
                is_secret=key_suffix in secret_keys,
                value_type=(
                    SettingType.BOOLEAN
                    if key_suffix in boolean_keys
                    else SettingType.NUMBER
                    if key_suffix in number_keys
                    else SettingType.STRING
                ),
                performed_by=current_user.username,
                audit_context=audit_context,
            )

        return ServiceNowConfigureResponse(
            instance_url=normalized["instance_url"],
            settings_saved=len(setting_values),
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@admin_router.post("/service-now/preview", response_model=ServiceNowPreviewResponse)
async def preview_service_now(request: ServiceNowPreviewRequest):
    try:
        result = await servicenow_provider.preview(
            config=request.model_dump(exclude={"item"}),
            item=request.item,
        )
        return ServiceNowPreviewResponse(
            provider_id=result.provider_id,
            cache_key=result.cache_key,
            enrichment_data=result.enrichment_data,
            aliases=[asdict(alias) for alias in result.aliases],
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ServiceNow request failed with status {exc.response.status_code}",
        )
    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ServiceNow request failed with status {status_code}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
