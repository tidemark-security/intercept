from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import SettingsService


@dataclass(frozen=True)
class AttachmentLimits:
    max_upload_size_mb: int
    max_image_preview_size_mb: int
    max_text_preview_size_mb: int
    allowed_file_types: tuple[str, ...]
    denied_file_types: tuple[str, ...]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_image_preview_size_bytes(self) -> int:
        return self.max_image_preview_size_mb * 1024 * 1024

    @property
    def max_text_preview_size_bytes(self) -> int:
        return self.max_text_preview_size_mb * 1024 * 1024


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return default

    return resolved if resolved > 0 else default


def _coerce_str_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


async def get_attachment_limits(db: AsyncSession) -> AttachmentLimits:
    settings_service = SettingsService(db)  # type: ignore[arg-type]

    max_upload_size_mb = _coerce_positive_int(
        await settings_service.get("storage.max_upload_size_mb", 50),
        50,
    )
    max_image_preview_size_mb = _coerce_positive_int(
        await settings_service.get("storage.max_image_preview_size_mb", 5),
        5,
    )
    max_text_preview_size_mb = _coerce_positive_int(
        await settings_service.get("storage.max_text_preview_size_mb", 1),
        1,
    )
    # Defaults come from the settings registry (storage.allowed_file_types /
    # storage.denied_file_types) when no env var or DB override is present.
    allowed_file_types = _coerce_str_list(
        await settings_service.get("storage.allowed_file_types", []),
    )
    denied_file_types = _coerce_str_list(
        await settings_service.get("storage.denied_file_types", []),
    )

    return AttachmentLimits(
        max_upload_size_mb=max_upload_size_mb,
        max_image_preview_size_mb=max_image_preview_size_mb,
        max_text_preview_size_mb=max_text_preview_size_mb,
        allowed_file_types=allowed_file_types,
        denied_file_types=denied_file_types,
    )