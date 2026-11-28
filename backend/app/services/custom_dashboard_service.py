"""Persistence and visibility for custom dashboard definitions."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_models import CustomDashboardRead, DashboardDefinition, DashboardSummary, DashboardUpdate, DashboardWrite
from app.models.enums import UserRole
from app.models.models import CustomDashboard, UserAccount
from app.services.audit_service import AuditContext, get_audit_service
from app.services.dashboard_catalog import validate_definition

STARTERS = {
    item["id"]: CustomDashboardRead(**item, scope="starter", revision=0, can_edit=False)
    for item in json.loads(Path(__file__).with_name("dashboard_starters.json").read_text(encoding="utf-8"))
}
for starter in STARTERS.values():
    validate_definition(starter.definition)


class DashboardNotFound(Exception):
    pass


class DashboardForbidden(Exception):
    pass


class DashboardConflict(Exception):
    pass


def _visible_to(user: UserAccount):
    return or_(CustomDashboard.owner_id == user.id, CustomDashboard.scope == "organization")


def _can_edit(row: CustomDashboard, user: UserAccount) -> bool:
    if row.scope == "organization":
        return user.role == UserRole.ADMIN
    return row.owner_id == user.id and user.role != UserRole.AUDITOR


def _read(row: CustomDashboard, user: UserAccount) -> CustomDashboardRead:
    return CustomDashboardRead(
        id=str(row.id), title=row.title, scope=row.scope, revision=row.revision,
        can_edit=_can_edit(row, user), definition=DashboardDefinition.model_validate(row.definition),
    )


async def _find(db: AsyncSession, identifier: str, user: UserAccount, *, lock: bool = False) -> CustomDashboard:
    try:
        dashboard_id = UUID(identifier)
    except ValueError as exc:
        raise DashboardNotFound() from exc
    query = select(CustomDashboard).where(CustomDashboard.id == dashboard_id, _visible_to(user))
    if lock:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None:
        raise DashboardNotFound()
    return row


async def list_dashboards(db: AsyncSession, user: UserAccount) -> list[DashboardSummary]:
    rows = (await db.scalars(select(CustomDashboard).where(_visible_to(user)).order_by(
        CustomDashboard.title, CustomDashboard.id,
    ))).all()
    summaries = [
        DashboardSummary(id=str(row.id), title=row.title, scope=row.scope, revision=row.revision, can_edit=_can_edit(row, user))
        for row in rows
    ]
    return [*STARTERS.values(), *summaries]


async def get_dashboard(db: AsyncSession, identifier: str, user: UserAccount) -> CustomDashboardRead:
    if identifier in STARTERS:
        return STARTERS[identifier]
    return _read(await _find(db, identifier, user), user)


def _check_write(user: UserAccount, scope: str) -> None:
    if user.role == UserRole.AUDITOR or (scope == "organization" and user.role != UserRole.ADMIN):
        raise DashboardForbidden()


async def _audit(db, row, user, action, context, old=None):
    current = {"title": row.title, "scope": row.scope, "revision": row.revision}
    await get_audit_service(db).log_event(
        event_type=f"dashboard.{action}", entity_type="dashboard", entity_id=str(row.id), performed_by=user.username,
        old_value=old, new_value=current if action != "deleted" else None, context=context,
    )


async def create_dashboard(db: AsyncSession, payload: DashboardWrite, user: UserAccount, context: AuditContext):
    _check_write(user, payload.scope)
    validate_definition(payload.definition)
    row = CustomDashboard(
        title=payload.title, scope=payload.scope, owner_id=user.id if payload.scope == "personal" else None,
        definition=payload.definition.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    await _audit(db, row, user, "published" if row.scope == "organization" else "created", context)
    return _read(row, user)


async def update_dashboard(
    db: AsyncSession, identifier: str, payload: DashboardUpdate, user: UserAccount, context: AuditContext,
):
    _check_write(user, payload.scope)
    row = await _find(db, identifier, user, lock=True)
    if not _can_edit(row, user):
        raise DashboardForbidden()
    if row.revision != payload.revision:
        raise DashboardConflict()
    validate_definition(payload.definition)
    old = {"title": row.title, "scope": row.scope, "revision": row.revision}
    row.title = payload.title
    row.scope = payload.scope
    row.owner_id = user.id if payload.scope == "personal" else None
    row.revision += 1
    row.updated_at = datetime.now(timezone.utc)
    row.definition = payload.definition.model_dump(mode="json")
    action = "published" if old["scope"] != row.scope and row.scope == "organization" else "updated"
    await _audit(db, row, user, action, context, old)
    return _read(row, user)


async def duplicate_dashboard(db: AsyncSession, identifier: str, title: str | None, user: UserAccount, context: AuditContext):
    source = await get_dashboard(db, identifier, user)
    payload = DashboardWrite(title=title or f"{source.title[:95]} copy", definition=source.definition)
    return await create_dashboard(db, payload, user, context)


async def delete_dashboard(db: AsyncSession, identifier: str, revision: int, user: UserAccount, context: AuditContext):
    row = await _find(db, identifier, user, lock=True)
    if not _can_edit(row, user):
        raise DashboardForbidden()
    if row.revision != revision:
        raise DashboardConflict()
    await _audit(db, row, user, "deleted", context, {"title": row.title, "scope": row.scope, "revision": row.revision})
    await db.delete(row)


async def evaluation_definition(db: AsyncSession, query, user: UserAccount):
    if query.dashboard_id is None:
        _check_write(user, "personal")
        return query.definition
    source = await get_dashboard(db, query.dashboard_id, user)
    if source.revision != query.revision:
        raise DashboardConflict()
    return query.definition if source.can_edit else source.definition
