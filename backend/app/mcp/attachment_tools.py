"""Signed uploads for attachments on an alert, case or task timeline."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from pydantic import Field, ValidationError

from app.services.timeline_attachment_service import (
    expected_attachment_upload_storage_prefix,
    find_attachment_item,
    finish_attachment_upload,
    normalize_upload_status,
    prepare_attachment_upload,
    sign_attachment_upload,
    validate_attachment_upload,
)
from app.core.database import async_session_factory
from app.core.entity_ids import format_entity_id
from app.core.id_parser import EntityIdParseError, parse_entity_id
from app.mcp.tools import _require_mcp_non_auditor_user_object
from app.models.enums import UploadStatus
from app.models.models import Alert, AttachmentStatusUpdate, Case, PresignedUploadRequest, Task
from app.models.search_schemas import EntityType
from app.services.alert_service import alert_service
from app.services.attachment_settings_service import get_attachment_limits
from app.services.case_service import case_service
from app.services.task_service import task_service
from app.services.timeline_add_service import (
    TimelineItemConflict,
    add_timeline_item_and_commit,
    find_timeline_authoring_retry,
    load_entity_for_timeline_update,
)
from app.services.timeline_service import TimelineValidationError

ATTACHMENT_FIELDS = frozenset(PresignedUploadRequest.model_fields)

_TARGETS = {
    EntityType.ALERT: (Alert, alert_service),
    EntityType.CASE: (Case, case_service),
    EntityType.TASK: (Task, task_service),
}


async def add_timeline_attachment(
    *,
    target_kind: EntityType,
    target_id: str,
    item_id: str,
    fields: dict,
    commit: bool,
    created_at_override: datetime | None = None,
) -> dict:
    """Validate or initiate a signed upload, using the client item ID for retries."""
    try:
        entity_id, prefix = parse_entity_id(target_id, target_kind)
        if not item_id.strip():
            raise ToolError("item_id must be nonblank")
        client_item_id = item_id
        unsupported = fields.keys() - ATTACHMENT_FIELDS
        if unsupported:
            raise ToolError(f"Unsupported attachment fields: {', '.join(sorted(unsupported))}")
        request = PresignedUploadRequest.model_validate(fields)
        model, _ = _TARGETS[target_kind]
        user = _require_mcp_non_auditor_user_object() if commit else None

        async with async_session_factory() as db:
            entity = (
                await load_entity_for_timeline_update(
                    db, entity_type=target_kind.value, entity_id=entity_id,
                )
                if commit else await db.get(model, entity_id)
            )
            if entity is None:
                raise ToolError(f"{target_kind.value} {target_id} not found")

            metadata = {
                "target_kind": target_kind.value,
                "target_id": format_entity_id(entity_id, prefix),
                "item_type": "attachment",
                "client_item_id": client_item_id,
            }
            if not commit:
                await validate_attachment_upload(request, db)
                return {"mode": "dry_run", **metadata, "fields": request.model_dump(mode="json")}

            item = await find_timeline_authoring_retry(
                db,
                timeline_items=entity.timeline_items,
                entity_type=target_kind.value,
                entity_id=entity_id,
                client_item_id=client_item_id,
                item_type="attachment",
                owner_id=user.id,
            )
            if item is not None:
                if item.get("uploaded_by_user_id") != str(user.id):
                    raise ToolError("Only upload owner can renew the upload URL")
                actual_id = item["id"]
                status = normalize_upload_status(item.get("upload_status"))
                response = {
                    "mode": "committed", **metadata, "item_id": actual_id,
                    "upload_status": status, "created": False,
                }
                if status == UploadStatus.UPLOADING.value:
                    key = item.get("upload_storage_key")
                    prefix = expected_attachment_upload_storage_prefix(
                        target_kind.value, entity_id, actual_id,
                    )
                    if not isinstance(key, str) or not key.startswith(prefix):
                        raise ToolError("Attachment upload has an invalid staging key")
                    limits = await get_attachment_limits(db)
                    signed = await sign_attachment_upload(actual_id, key, limits.max_upload_size_bytes)
                    response.update(upload_url=signed.upload_url, expires_at=signed.expires_at.isoformat())
                return response

            max_file_size = await validate_attachment_upload(request, db)
            attachment = prepare_attachment_upload(
                entity_type=target_kind.value, parent_id=entity_id,
                request_data=request, current_user=user,
            )
            signed = await sign_attachment_upload(attachment.id, attachment.upload_storage_key, max_file_size)
            result = await add_timeline_item_and_commit(
                db,
                entity_id=entity_id,
                entity_type=target_kind.value,
                timeline_item=attachment,
                performed_by=user.username,
                created_at_override=created_at_override,
                retry_client_item_id=client_item_id,
                retry_user_id=user.id,
            )
            return {
                "mode": "committed", **metadata, "item_id": result.item["id"],
                "upload_status": UploadStatus.UPLOADING.value, "created": result.created,
                "upload_url": signed.upload_url, "expires_at": signed.expires_at.isoformat(),
            }
    except HTTPException as exc:
        raise ToolError(str(exc.detail)) from exc
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, err["loc"])) for err in exc.errors(include_input=False))
        raise ToolError(f"Invalid attachment fields: {fields}") from exc
    except (EntityIdParseError, TimelineItemConflict, TimelineValidationError) as exc:
        raise ToolError(str(exc)) from exc


async def finish_timeline_attachment(
    target_kind: EntityType,
    target_id: str,
    item_id: str,
    status: Literal["COMPLETE", "FAILED"],
    file_hash: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None,
) -> dict:
    """Finish an attachment upload as its owner. Repeating the same outcome is safe.

    Args:
        target_kind: The timeline's parent kind.
        target_id: Numeric or prefixed parent ID.
        item_id: Attachment timeline item ID returned when initiating the upload.
        status: COMPLETE verifies and publishes the uploaded file. FAILED ends the attempt.
        file_hash: Optional SHA-256 hex digest to verify for COMPLETE.
    """
    try:
        user = _require_mcp_non_auditor_user_object()
        entity_id, prefix = parse_entity_id(target_id, target_kind)
        if status not in ("COMPLETE", "FAILED"):
            raise ToolError("Attachment status must be COMPLETE or FAILED")
        _, service = _TARGETS[target_kind]
        async with async_session_factory() as db:
            updated = await finish_attachment_upload(
                entity_type=target_kind.value, parent_id=entity_id,
                item_id=item_id, db=db, service=service, current_user=user,
                update_data=AttachmentStatusUpdate(status=UploadStatus(status), file_hash=file_hash),
                replay_completed=True,
            )
            item = find_attachment_item(updated.timeline_items, item_id)
            return {
                "mode": "committed",
                "target_kind": target_kind.value,
                "target_id": format_entity_id(entity_id, prefix),
                "item_id": item_id,
                "upload_status": normalize_upload_status(item.get("upload_status")),
                "file_hash": item.get("file_hash"),
            }
    except HTTPException as exc:
        raise ToolError(str(exc.detail)) from exc
    except EntityIdParseError as exc:
        raise ToolError(str(exc)) from exc
