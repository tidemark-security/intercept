import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, List, Type
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user, require_authenticated_user
from app.core.database import get_db
from app.services.settings_service import SettingsService
from app.models.models import (
    LinkTemplate,
    LinkTemplateCreate,
    LinkTemplateExportBundle,
    LinkTemplateExportRequest,
    LinkTemplateRead,
    LinkTemplateResolveRequest,
    LinkTemplateUpdate,
    LinkTemplateVisibility,
    PersonalLinkTemplate,
    PersonalLinkTemplateCreate,
    PersonalLinkTemplateRead,
    PersonalLinkTemplateUpdate,
    PortableLinkTemplate,
    ResolvedLinkTemplateRead,
    UserAccount,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")
ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}
DENIED_URL_SCHEMES = {"data", "file", "javascript", "vbscript"}
PORTABLE_TEMPLATE_FIELDS = {
    "template_id",
    "name",
    "icon_name",
    "tooltip_template",
    "url_template",
    "field_names",
    "conditions",
    "surface_scopes",
    "entity_types",
    "enabled",
    "display_order",
}

router = APIRouter(
    prefix="/link-templates",
    tags=["link-templates"],
    dependencies=[Depends(require_authenticated_user)],
)
personal_router = APIRouter(
    prefix="/personal-link-templates",
    tags=["personal-link-templates"],
    dependencies=[Depends(require_authenticated_user)],
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


def _interpolate(template: str, item: dict, *, encode_values: bool) -> str | None:
    def replace(match: re.Match[str]) -> str:
        value = _get_path_value(item, match.group(1))
        if value is None:
            raise KeyError(match.group(1))
        rendered = str(value)
        return quote(rendered, safe="") if encode_values else rendered

    try:
        return PLACEHOLDER_PATTERN.sub(replace, template)
    except KeyError:
        return None


def _normalize_extra_url_schemes(value: Any) -> set[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    schemes: set[str] = set()
    for raw_value in raw_values:
        scheme = str(raw_value).strip().lower().rstrip(":")
        if re.fullmatch(r"[a-z][a-z0-9+.-]*", scheme) and scheme not in DENIED_URL_SCHEMES:
            schemes.add(scheme)
    return schemes


async def _get_allowed_url_schemes(db: AsyncSession) -> set[str]:
    settings = SettingsService(db)  # type: ignore[arg-type]
    return ALLOWED_URL_SCHEMES | _normalize_extra_url_schemes(
        await settings.get("link_templates.allowed_url_schemes_extra", [])
    )


def _is_safe_resolved_url(value: str | None, allowed_schemes: set[str] | None = None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    return scheme in (allowed_schemes or ALLOWED_URL_SCHEMES) and scheme not in DENIED_URL_SCHEMES


async def _validate_url_template_allowed(db: AsyncSession, value: str) -> None:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in await _get_allowed_url_schemes(db) or scheme in DENIED_URL_SCHEMES:
        raise HTTPException(status_code=422, detail=f"url_template uses disallowed URL scheme '{scheme or 'none'}'")


def _matches_template(
    template: LinkTemplate | PersonalLinkTemplate,
    item: dict,
    *,
    surface: str = "timeline_item",
    entity_type: str | None = None,
) -> bool:
    if surface not in (template.surface_scopes or []):
        return False

    if template.entity_types and entity_type not in template.entity_types:
        return False

    if template.conditions:
        for field, expected in template.conditions.items():
            if _get_path_value(item, field) != expected:
                return False

    if template.field_names:
        return any(_get_path_value(item, field) is not None for field in template.field_names)

    return True


def _template_to_portable(template: LinkTemplate | PersonalLinkTemplate) -> PortableLinkTemplate:
    return PortableLinkTemplate.model_validate(
        {field: getattr(template, field) for field in PORTABLE_TEMPLATE_FIELDS}
    )


def _templates_to_bundle(templates: Iterable[LinkTemplate | PersonalLinkTemplate]) -> LinkTemplateExportBundle:
    return LinkTemplateExportBundle(
        schema_version=1,
        templates=[_template_to_portable(template) for template in templates],
    )


def _extract_portable_templates(payload: Any) -> List[PortableLinkTemplate]:
    raw_templates: Any
    if isinstance(payload, list):
        raw_templates = payload
    elif isinstance(payload, dict) and "templates" in payload:
        schema_version = payload.get("schema_version", 1)
        if schema_version != 1:
            raise HTTPException(status_code=422, detail="Unsupported link template schema_version")
        raw_templates = payload["templates"]
    elif isinstance(payload, dict):
        raw_templates = [payload]
    else:
        raise HTTPException(status_code=422, detail="Import payload must be a template or template bundle")

    if not isinstance(raw_templates, list) or not raw_templates:
        raise HTTPException(status_code=422, detail="Import payload must contain at least one template")

    templates: List[PortableLinkTemplate] = []
    for raw_template in raw_templates:
        try:
            templates.append(PortableLinkTemplate.model_validate(raw_template))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return templates


def _with_copy_suffix(template_id: str, existing_ids: set[str]) -> str:
    if template_id not in existing_ids:
        return template_id
    candidate = f"{template_id}-copy"
    if candidate not in existing_ids:
        return candidate
    index = 2
    while True:
        candidate = f"{template_id}-copy-{index}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def _copy_name(name: str) -> str:
    return name if name.endswith(" (copy)") else f"{name} (copy)"


async def _import_templates(
    *,
    db: AsyncSession,
    payload: Any,
    model: Type[LinkTemplate] | Type[PersonalLinkTemplate],
    read_model: Type[LinkTemplateRead] | Type[PersonalLinkTemplateRead],
    user_id: Any = None,
) -> list[LinkTemplateRead] | list[PersonalLinkTemplateRead]:
    portable_templates = _extract_portable_templates(payload)
    for portable_template in portable_templates:
        await _validate_url_template_allowed(db, portable_template.url_template)

    query = select(model.template_id)
    if model is PersonalLinkTemplate:
        query = query.where(PersonalLinkTemplate.user_id == user_id)
    result = await db.execute(query)
    existing_ids = set(result.scalars().all())

    created: list[LinkTemplate | PersonalLinkTemplate] = []
    for portable_template in portable_templates:
        data = portable_template.model_dump()
        next_template_id = _with_copy_suffix(portable_template.template_id, existing_ids)
        if next_template_id != portable_template.template_id:
            data["template_id"] = next_template_id
            data["name"] = _copy_name(portable_template.name)
        existing_ids.add(data["template_id"])

        if model is PersonalLinkTemplate:
            data["user_id"] = user_id

        template = model(**data)
        db.add(template)
        created.append(template)

    await db.commit()
    for template in created:
        await db.refresh(template)
    return [read_model.model_validate(template) for template in created]


async def _get_owned_personal_template(
    template_id: int,
    db: AsyncSession,
    current_user: UserAccount,
) -> PersonalLinkTemplate:
    result = await db.execute(
        select(PersonalLinkTemplate).where(
            PersonalLinkTemplate.id == template_id,
            PersonalLinkTemplate.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail=f"Personal link template {template_id} not found")
    return template


@router.get("", response_model=List[LinkTemplateRead])
async def get_link_templates(
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Get public link templates."""
    query = select(LinkTemplate).order_by(LinkTemplate.display_order, LinkTemplate.name)
    if enabled_only:
        query = query.where(LinkTemplate.enabled == True)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/export", response_model=LinkTemplateExportBundle)
async def export_link_templates(
    request: LinkTemplateExportRequest,
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin_user),
):
    """Export selected public link templates as a portable JSON bundle."""
    if not request.template_ids:
        raise HTTPException(status_code=422, detail="template_ids must contain at least one template id")

    result = await db.execute(
        select(LinkTemplate)
        .where(LinkTemplate.id.in_(request.template_ids))
        .order_by(LinkTemplate.display_order, LinkTemplate.name)
    )
    templates = result.scalars().all()
    found_ids = {template.id for template in templates}
    missing_ids = [template_id for template_id in request.template_ids if template_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Link templates not found: {missing_ids}")
    return _templates_to_bundle(templates)


@router.post("/import", response_model=List[LinkTemplateRead])
async def import_link_templates(
    payload: Any = Body(...),
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin_user),
):
    """Import public link templates from a portable single-template or bundle payload."""
    return await _import_templates(
        db=db,
        payload=payload,
        model=LinkTemplate,
        read_model=LinkTemplateRead,
    )


@router.post("/resolve", response_model=List[ResolvedLinkTemplateRead])
async def resolve_link_templates(
    request: LinkTemplateResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Resolve enabled public and current-user personal templates for one context."""
    public_result = await db.execute(
        select(LinkTemplate)
        .where(LinkTemplate.enabled == True)
        .order_by(LinkTemplate.display_order, LinkTemplate.name)
    )
    personal_result = await db.execute(
        select(PersonalLinkTemplate)
        .where(
            PersonalLinkTemplate.user_id == current_user.id,
            PersonalLinkTemplate.enabled == True,
        )
        .order_by(PersonalLinkTemplate.display_order, PersonalLinkTemplate.name)
    )

    context = dict(request.item or {})
    context["surface"] = request.surface
    if request.entity_type:
        context["entity_type"] = request.entity_type
    allowed_schemes = await _get_allowed_url_schemes(db)

    candidates: list[tuple[LinkTemplate | PersonalLinkTemplate, LinkTemplateVisibility]] = [
        *((template, "PUBLIC") for template in public_result.scalars().all()),
        *((template, "PERSONAL") for template in personal_result.scalars().all()),
    ]

    resolved_links: List[ResolvedLinkTemplateRead] = []
    for template, visibility in sorted(candidates, key=lambda candidate: (candidate[0].display_order, candidate[0].name)):
        if not _matches_template(
            template,
            context,
            surface=request.surface,
            entity_type=request.entity_type,
        ):
            continue

        url = _interpolate(template.url_template, context, encode_values=True)
        tooltip = _interpolate(template.tooltip_template, context, encode_values=False)
        if not _is_safe_resolved_url(url, allowed_schemes) or tooltip is None:
            continue

        resolved_links.append(
            ResolvedLinkTemplateRead(
                id=template.id,
                visibility=visibility,
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
    db: AsyncSession = Depends(get_db),
):
    """Get one public link template."""
    template = await db.get(LinkTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Link template {template_id} not found")
    return template


@router.post("", response_model=LinkTemplateRead)
async def create_link_template(
    template_data: LinkTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin_user),
):
    """Create a public link template."""
    await _validate_url_template_allowed(db, template_data.url_template)
    result = await db.execute(select(LinkTemplate).where(LinkTemplate.template_id == template_data.template_id))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Link template with template_id '{template_data.template_id}' already exists",
        )

    template = LinkTemplate(**template_data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    logger.info("Created public link template %s (id=%s)", template.template_id, template.id)
    return template


@router.patch("/{template_id}", response_model=LinkTemplateRead)
async def update_link_template(
    template_id: int,
    template_data: LinkTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin_user),
):
    """Update a public link template."""
    template = await db.get(LinkTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Link template {template_id} not found")

    update_dict = template_data.model_dump(exclude_unset=True)
    if "url_template" in update_dict:
        await _validate_url_template_allowed(db, update_dict["url_template"])
    for key, value in update_dict.items():
        setattr(template, key, value)
    template.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(template)
    logger.info("Updated public link template %s (id=%s)", template.template_id, template.id)
    return template


@router.delete("/{template_id}")
async def delete_link_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin_user),
):
    """Delete a public link template."""
    template = await db.get(LinkTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Link template {template_id} not found")

    await db.delete(template)
    await db.commit()
    logger.info("Deleted public link template %s (id=%s)", template.template_id, template_id)
    return {"message": f"Link template {template_id} deleted successfully"}


@personal_router.get("", response_model=List[PersonalLinkTemplateRead])
async def get_personal_link_templates(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get the current user's personal link templates."""
    query = (
        select(PersonalLinkTemplate)
        .where(PersonalLinkTemplate.user_id == current_user.id)
        .order_by(PersonalLinkTemplate.display_order, PersonalLinkTemplate.name)
    )
    if enabled_only:
        query = query.where(PersonalLinkTemplate.enabled == True)
    result = await db.execute(query)
    return result.scalars().all()


@personal_router.post("/export", response_model=LinkTemplateExportBundle)
async def export_personal_link_templates(
    request: LinkTemplateExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Export selected current-user personal link templates as a portable JSON bundle."""
    if not request.template_ids:
        raise HTTPException(status_code=422, detail="template_ids must contain at least one template id")

    result = await db.execute(
        select(PersonalLinkTemplate)
        .where(
            PersonalLinkTemplate.user_id == current_user.id,
            PersonalLinkTemplate.id.in_(request.template_ids),
        )
        .order_by(PersonalLinkTemplate.display_order, PersonalLinkTemplate.name)
    )
    templates = result.scalars().all()
    found_ids = {template.id for template in templates}
    missing_ids = [template_id for template_id in request.template_ids if template_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Personal link templates not found: {missing_ids}")
    return _templates_to_bundle(templates)


@personal_router.post("/import", response_model=List[PersonalLinkTemplateRead])
async def import_personal_link_templates(
    payload: Any = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Import current-user personal templates from a portable single-template or bundle payload."""
    return await _import_templates(
        db=db,
        payload=payload,
        model=PersonalLinkTemplate,
        read_model=PersonalLinkTemplateRead,
        user_id=current_user.id,
    )


@personal_router.get("/{template_id}", response_model=PersonalLinkTemplateRead)
async def get_personal_link_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get one current-user personal link template."""
    return await _get_owned_personal_template(template_id, db, current_user)


@personal_router.post("", response_model=PersonalLinkTemplateRead)
async def create_personal_link_template(
    template_data: PersonalLinkTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Create a current-user personal link template."""
    await _validate_url_template_allowed(db, template_data.url_template)
    result = await db.execute(
        select(PersonalLinkTemplate).where(
            PersonalLinkTemplate.user_id == current_user.id,
            PersonalLinkTemplate.template_id == template_data.template_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Personal link template with template_id '{template_data.template_id}' already exists",
        )

    template = PersonalLinkTemplate(**template_data.model_dump(), user_id=current_user.id)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    logger.info(
        "Created personal link template %s (id=%s, user_id=%s)",
        template.template_id,
        template.id,
        current_user.id,
    )
    return template


@personal_router.patch("/{template_id}", response_model=PersonalLinkTemplateRead)
async def update_personal_link_template(
    template_id: int,
    template_data: PersonalLinkTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Update a current-user personal link template."""
    template = await _get_owned_personal_template(template_id, db, current_user)

    update_dict = template_data.model_dump(exclude_unset=True)
    if "url_template" in update_dict:
        await _validate_url_template_allowed(db, update_dict["url_template"])
    for key, value in update_dict.items():
        setattr(template, key, value)
    template.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(template)
    return template


@personal_router.delete("/{template_id}", status_code=204)
async def delete_personal_link_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Delete a current-user personal link template."""
    template = await _get_owned_personal_template(template_id, db, current_user)
    await db.delete(template)
    await db.commit()
