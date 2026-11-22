"""Timeline attachment upload validation, signed URLs, and verified finalization."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.models import (
        AttachmentItem,
        AttachmentStatusUpdate,
        PresignedUploadRequest,
        PresignedUploadResponse,
        UserAccount,
    )

logger = logging.getLogger(__name__)


def normalize_upload_status(status: Any, default: str = "COMPLETE") -> str:
    """Normalize stored attachment upload status values for route checks."""
    if status is None:
        return default

    if hasattr(status, "value"):
        status = status.value

    normalized = str(status).strip()
    if not normalized:
        return default

    return normalized.upper()


def expected_attachment_storage_prefix(entity_type: str, parent_id: int, item_id: str) -> str:
    return f"{entity_type}s/{parent_id}/attachments/{item_id}/"


def expected_attachment_upload_storage_prefix(entity_type: str, parent_id: int, item_id: str) -> str:
    return f"_uploads/{entity_type}s/{parent_id}/attachments/{item_id}/"


@dataclass(frozen=True)
class AttachmentFinalization:
    """Validated storage result prepared for one timeline transaction."""

    file_hash: str
    companion_timeline_item: Any | None = None


def find_attachment_item(
    timeline_items: Optional[List[Dict[str, Any]] | Dict[str, Dict[str, Any]]], item_id: str
) -> Optional[Dict[str, Any]]:
    """Find an attachment timeline item by ID."""
    if isinstance(timeline_items, dict):
        items = timeline_items.values()
    elif isinstance(timeline_items, list):
        items = timeline_items
    else:
        return None
    for item in items:
        if (
            isinstance(item, dict)
            and item.get("id") == item_id
            and item.get("type") == "attachment"
        ):
            return item
    return None


async def validate_attachment_upload(
    request_data: "PresignedUploadRequest",
    db: AsyncSession,
) -> int:
    """Validate an upload declaration and return the current size limit."""
    from app.services.attachment_settings_service import get_attachment_limits
    from app.services.storage_service import storage_service

    limits = await get_attachment_limits(db)
    if request_data.file_size > limits.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size {request_data.file_size} exceeds limit {limits.max_upload_size_mb}MB",
        )
    if not storage_service.validate_file_type(
        request_data.mime_type, limits.allowed_file_types, limits.denied_file_types,
    ):
        raise HTTPException(
            status_code=415,
            detail=f"File type {request_data.mime_type} not allowed",
        )
    return limits.max_upload_size_bytes


def prepare_attachment_upload(
    *,
    entity_type: str,
    parent_id: int,
    request_data: "PresignedUploadRequest",
    current_user: "UserAccount",
) -> "AttachmentItem":
    """Prepare a server-owned timeline item and allocate its object keys."""
    from app.models.enums import UploadStatus
    from app.models.models import AttachmentItem
    from app.services.storage_service import storage_service

    parent_type = f"{entity_type}s"
    item_id = str(uuid.uuid4())
    filename = storage_service.sanitize_filename(request_data.filename)
    return AttachmentItem(
        id=item_id,
        type="attachment",
        description=request_data.description,
        file_name=filename,
        mime_type=request_data.mime_type,
        file_size=request_data.file_size,
        storage_key=storage_service.generate_storage_key(
            parent_id, item_id, filename, parent_type=parent_type,
        ),
        upload_storage_key=storage_service.generate_upload_storage_key(
            parent_id, item_id, parent_type=parent_type,
        ),
        upload_status=UploadStatus.UPLOADING,
        uploaded_by=current_user.username,
        uploaded_by_user_id=str(current_user.id),
        created_by=current_user.username,
        timestamp=request_data.timestamp or datetime.now(timezone.utc),
        tags=request_data.tags or [],
    )


async def sign_attachment_upload(
    item_id: str,
    upload_storage_key: str,
    max_file_size: int,
) -> "PresignedUploadResponse":
    from app.core.storage_config import storage_config
    from app.models.models import PresignedUploadResponse
    from app.services.storage_service import storage_service

    lifetime = storage_config.upload_timeout_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=lifetime)
    upload_url = await storage_service.generate_presigned_upload_url(
        upload_storage_key, expires_minutes=lifetime,
    )
    return PresignedUploadResponse(
        item_id=item_id,
        upload_url=upload_url,
        storage_key=upload_storage_key,
        expires_at=expires_at,
        max_file_size=max_file_size,
    )


def _attachment_expected_size(timeline_item: Dict[str, Any]) -> int:
    try:
        expected_size = int(timeline_item.get("file_size"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=409,
            detail="Attachment has invalid expected file size",
        )
    if expected_size <= 0:
        raise HTTPException(
            status_code=409,
            detail="Attachment has invalid expected file size",
        )
    return expected_size


async def _delete_attachment_object_best_effort(
    storage_key: str,
    *,
    description: str,
) -> None:
    from app.services.storage_service import storage_service

    try:
        await storage_service.delete_file(storage_key)
    except Exception:  # pragma: no cover - best-effort external cleanup
        logger.warning("Failed to clean up %s %s", description, storage_key)


async def _finalize_attachment_upload(
    *,
    entity_type: str,
    parent_id: int,
    item_id: str,
    timeline_item: Dict[str, Any],
    requested_file_hash: str | None,
    created_by: str,
    db: AsyncSession,
) -> AttachmentFinalization:
    """Copy and validate a staged object without mutating database state."""
    from app.services.attachment_settings_service import get_attachment_limits
    from app.services.email_evidence_service import (
        EmailEvidenceParseError,
        build_email_timeline_item,
        is_email_evidence_file,
        parse_email_evidence,
    )
    from app.services.storage_service import storage_service

    storage_key = timeline_item.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=400, detail="Attachment has no storage key")
    storage_key = str(storage_key)
    if not storage_key.startswith(
        expected_attachment_storage_prefix(entity_type, parent_id, item_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Attachment storage key does not belong to this entity",
        )

    staged_storage_key = timeline_item.get("upload_storage_key")
    if not staged_storage_key:
        raise HTTPException(
            status_code=409,
            detail="Attachment upload must be restarted before it can be finalized",
        )
    staged_storage_key = str(staged_storage_key)
    if not staged_storage_key.startswith(
        expected_attachment_upload_storage_prefix(entity_type, parent_id, item_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Attachment upload storage key does not belong to this entity",
        )

    if not await storage_service.verify_file_exists(staged_storage_key):
        raise HTTPException(status_code=409, detail="File not found in storage")

    expected_size = _attachment_expected_size(timeline_item)
    attachment_limits = await get_attachment_limits(db)
    if expected_size > attachment_limits.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size {expected_size} exceeds limit "
                f"{attachment_limits.max_upload_size_mb}MB"
            ),
        )

    upload_metadata = await storage_service.get_object_metadata(staged_storage_key)
    if upload_metadata.size > attachment_limits.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Uploaded file size {upload_metadata.size} exceeds limit "
                f"{attachment_limits.max_upload_size_mb}MB"
            ),
        )
    if upload_metadata.size != expected_size:
        raise HTTPException(
            status_code=409,
            detail="Uploaded file size does not match the expected size",
        )

    await storage_service.copy_object(staged_storage_key, storage_key)
    try:
        final_metadata = await storage_service.get_object_metadata(
            storage_key,
            require_checksum=True,
        )
        if final_metadata.size != expected_size:
            raise HTTPException(
                status_code=409,
                detail="Finalized file size does not match the expected size",
            )
        if not final_metadata.sha256:
            raise HTTPException(
                status_code=409,
                detail="Storage did not return a SHA256 checksum for the finalized file",
            )

        detected_mime_type = await storage_service.detect_mime_type(storage_key)
        if not storage_service.validate_file_type(
            detected_mime_type,
            attachment_limits.allowed_file_types,
            attachment_limits.denied_file_types,
        ):
            raise HTTPException(
                status_code=415,
                detail=f"Detected file type {detected_mime_type} not allowed",
            )
        declared_mime_type = storage_service.normalize_mime_type(
            timeline_item.get("mime_type")
        )
        if storage_service.normalize_mime_type(detected_mime_type) != declared_mime_type:
            raise HTTPException(
                status_code=415,
                detail="Uploaded file content type does not match the declared MIME type",
            )
        if (
            requested_file_hash
            and requested_file_hash.lower() != final_metadata.sha256
        ):
            raise HTTPException(
                status_code=409,
                detail="Uploaded file hash does not match the stored object",
            )

        companion_timeline_item = None
        if entity_type == "case" and is_email_evidence_file(
            timeline_item.get("file_name"),
            detected_mime_type,
        ):
            try:
                email_bytes = await storage_service.get_object_bytes(
                    storage_key,
                    max_bytes=expected_size,
                )
                parsed_email = await asyncio.to_thread(
                    parse_email_evidence,
                    email_bytes,
                    timeline_item.get("file_name"),
                    detected_mime_type,
                )
                companion_timeline_item = build_email_timeline_item(
                    parsed_email,
                    created_by=created_by,
                )
            except EmailEvidenceParseError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        await _delete_attachment_object_best_effort(
            storage_key,
            description="rejected finalized attachment",
        )
        raise

    return AttachmentFinalization(
        file_hash=final_metadata.sha256,
        companion_timeline_item=companion_timeline_item,
    )


async def finish_attachment_upload(
    *,
    entity_type: str,
    parent_id: int,
    item_id: str,
    update_data: "AttachmentStatusUpdate",
    current_user: "UserAccount",
    db: AsyncSession,
    service: Any,
    replay_completed: bool = False,
) -> Any:
    """Shared logic for updating an attachment's upload status.

    ``service`` must expose ``update_timeline_item(db, parent_id, item_id, item, username)``.
    Returns the updated entity.
    """
    from app.models.enums import UploadStatus
    from app.models.models import AttachmentItem
    from app.services.timeline_add_service import TimelineItemConflict, load_entity_for_timeline_update
    from app.services.timeline_service import attachment_storage_writes

    try:
        # Lock across storage finalization so parallel HTTP and MCP requests
        # cannot copy or remove the same finalized object concurrently.
        entity = await load_entity_for_timeline_update(
            db, entity_type=entity_type, entity_id=parent_id,
        )
        if entity is None:
            raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} {parent_id} not found")
        timeline_item = find_attachment_item(entity.timeline_items, item_id)
        if not timeline_item:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment item {item_id} not found",
            )

        expected_item_fields = {
            "upload_status": timeline_item.get("upload_status"),
            "upload_storage_key": timeline_item.get("upload_storage_key"),
        }

        if timeline_item.get("uploaded_by_user_id"):
            owner_matches = timeline_item.get("uploaded_by_user_id") == str(current_user.id)
        else:
            owner_matches = timeline_item.get("uploaded_by") == current_user.username
        if not owner_matches:
            raise HTTPException(
                status_code=403,
                detail="Only upload owner can update status",
            )

        current_status = normalize_upload_status(timeline_item.get("upload_status"))
        if current_status in [UploadStatus.COMPLETE.value, UploadStatus.FAILED.value]:
            if replay_completed:
                if current_status != update_data.status:
                    raise HTTPException(
                        status_code=409, detail=f"Attachment upload already ended with status {current_status}",
                    )
                if (
                    update_data.file_hash
                    and current_status == UploadStatus.COMPLETE.value
                    and update_data.file_hash.lower() != timeline_item.get("file_hash")
                ):
                    raise HTTPException(status_code=409, detail="Uploaded file hash does not match the stored object")
                return entity
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {current_status} to {update_data.status}",
            )

        companion_timeline_item = None

        if update_data.status == UploadStatus.COMPLETE:
            finalization = await _finalize_attachment_upload(
                entity_type=entity_type,
                parent_id=parent_id,
                item_id=item_id,
                timeline_item=timeline_item,
                requested_file_hash=update_data.file_hash,
                created_by=current_user.username,
                db=db,
            )
            timeline_item["file_hash"] = finalization.file_hash
            # Keep this field explicitly set so attachment updates using
            # ``exclude_unset`` clear the staged key instead of merging the
            # previous value back into the completed attachment.
            timeline_item["upload_storage_key"] = None
            companion_timeline_item = finalization.companion_timeline_item

        if replay_completed and update_data.status == UploadStatus.FAILED:
            timeline_item["upload_storage_key"] = None
        timeline_item["upload_status"] = update_data.status.value

        attachment_item = AttachmentItem(**timeline_item)

        update_kwargs = {
            "expected_item_fields": expected_item_fields,
        }
        if companion_timeline_item is not None:
            update_kwargs["companion_timeline_item"] = companion_timeline_item
        with attachment_storage_writes(item_id):
            updated = await service.update_timeline_item(
                db,
                parent_id,
                item_id,
                attachment_item,
                current_user.username,
                **update_kwargs,
            )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Attachment item {item_id} not found")

        logger.info(
            "Updated attachment status for %s %s, item %s, status %s, user %s",
            entity_type, parent_id, item_id, update_data.status, current_user.username,
        )

        return updated

    except TimelineItemConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Error updating attachment status for %s %s, item %s",
            entity_type,
            parent_id,
            item_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update attachment status",
        )
