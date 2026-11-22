"""Discover and author typed items using Intercept's timeline models."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.route_utils import create_timeline_converter, get_timeline_item_types
from app.api.timestamp_overrides import normalize_created_at_override
from app.core.database import async_session_factory
from app.core.entity_ids import TASK_PREFIX, format_entity_id
from app.core.id_parser import EntityIdParseError, parse_entity_id
from app.mcp.tools import (
    _get_authenticated_user,
    _get_authenticated_username,
    _require_mcp_non_auditor_user_object,
    add_timeline_item_tool,
)
from app.models.enums import ActorType
from app.models.models import (
    Actor,
    Alert,
    AlertTimelineItem,
    Case,
    CaseTimelineItem,
    PresignedUploadRequest,
    Task,
    TaskTimelineItem,
)
from app.models.search_schemas import EntityType
from app.services.mcp_service import _existing_timeline_item_output
from app.services.tag_filter_utils import ProtectedTagMutationError, validate_protected_tag_mutation
from app.services.timeline_add_service import (
    TimelineItemConflict,
    add_timeline_item_and_commit,
    find_timeline_authoring_retry,
)
from app.services.timeline_service import TimelineValidationError, timeline_service

TimelineItemType = Literal[
    "note", "internal_actor", "external_actor", "threat_actor", "alert",
    "attachment", "case", "email", "forensic_artifact", "link",
    "network_traffic", "observable", "process", "registry_change", "system",
    "task", "ttp",
]

_TARGETS = {
    "alert": (Alert, AlertTimelineItem),
    "case": (Case, CaseTimelineItem),
    "task": (Task, TaskTimelineItem),
}
_TYPES = {
    kind: {
        name: model
        for name, model in get_timeline_item_types(union).items()
        if name != "deleted"
    }
    for kind, (_, union) in _TARGETS.items()
}
_CONVERTERS = {kind: create_timeline_converter(models) for kind, models in _TYPES.items()}
_COMMON_FIELDS = {"description", "timestamp", "tags", "flagged", "highlighted", "parent_id"}
_TYPE_FIELDS = {
    "note": (),
    "internal_actor": (
        "actor_id", "user_id", "name", "title", "org", "contact_phone", "contact_email",
        "manager_id", "is_vip", "is_privileged", "is_high_risk", "is_contractor", "is_service_account",
    ),
    "external_actor": ("actor_id", "name", "title", "org", "contact_phone", "contact_email"),
    "threat_actor": ("actor_id", "name", "title", "org", "contact_phone", "contact_email", "tag_id", "confidence"),
    "alert": ("alert_id",),
    "case": ("case_id",),
    "email": ("sender", "recipient", "subject", "message_id"),
    "forensic_artifact": ("hash", "hash_type", "url"),
    "link": ("url",),
    "network_traffic": (
        "source_ip", "destination_ip", "source_port", "destination_port", "protocol",
        "bytes_sent", "bytes_received", "duration",
    ),
    "observable": ("observable_type", "observable_value"),
    "process": ("process_name", "process_id", "parent_process_id", "command_line", "user_account", "duration", "exit_code"),
    "registry_change": ("registry_key", "registry_value", "old_data", "new_data", "operation", "user_account"),
    "system": (
        "hostname", "ip_address", "system_type", "cmdb_id", "is_critical",
        "is_internet_facing", "is_high_risk", "is_legacy", "is_privileged",
    ),
    "task": ("title", "status", "priority", "assignee", "due_date", "picerl_stage"),
    "ttp": ("mitre_id",),
}
_EXAMPLES = {
    "note": {"description": "Reviewed the alert with the incident lead."},
    "internal_actor": {"user_id": "analyst@example.com"},
    "external_actor": {"name": "Example Vendor", "org": "Example"},
    "threat_actor": {"name": "Unknown Group", "confidence": 45},
    "alert": {"alert_id": 123},
    "attachment": {"filename": "report.txt", "file_size": 12, "mime_type": "text/plain"},
    "case": {"case_id": 123},
    "email": {"sender": "a@example.com", "recipient": "b@example.com", "subject": "Incident update"},
    "forensic_artifact": {"url": "https://example.com/artifact"},
    "link": {"url": "https://example.com/report"},
    "network_traffic": {"source_ip": "192.0.2.5", "destination_ip": "198.51.100.10"},
    "observable": {"observable_type": "IP", "observable_value": "192.0.2.5"},
    "process": {"process_name": "example.exe", "process_id": 1001},
    "registry_change": {"registry_key": r"HKLM\Software\Example", "operation": "MODIFY"},
    "system": {"hostname": "workstation.example.com"},
    "task": {"title": "Review incident evidence", "picerl_stage": "Identification"},
    "ttp": {"mitre_id": "T1059"},
}
_REQUIRED_FIELDS = {
    "note": ("description",),
    "alert": ("alert_id",),
    "case": ("case_id",),
    "email": ("sender", "recipient", "subject"),
    "link": ("url",),
    "network_traffic": ("source_ip", "destination_ip"),
    "observable": ("observable_type", "observable_value"),
    "process": ("process_name",),
    "registry_change": ("registry_key",),
    "system": ("hostname",),
    "task": ("title",),
    "ttp": ("mitre_id",),
}
_ANY_OF = {
    "internal_actor": ("actor_id", "user_id"),
    "external_actor": ("actor_id", "name"),
    "threat_actor": ("actor_id", "name", "tag_id"),
    "forensic_artifact": ("hash", "url"),
}
_ACTOR_TYPES = {
    "internal_actor": ActorType.INTERNAL,
    "external_actor": ActorType.EXTERNAL,
    "threat_actor": ActorType.EXTERNAL_THREAT,
}
_SIDE_EFFECTS = {
    "alert": "Adds a timeline reference to the existing alert.",
    "case": "Adds a timeline reference to the existing case.",
    "attachment": "Creates a pending attachment and returns a presigned PUT URL. Finalize with finish_timeline_attachment.",
    "task": "Creates a first-class task linked to the case, with a canonical linked-task timeline item.",
    "observable": "May queue configured enrichment for the observable.",
    "system": "May queue configured system enrichment.",
    "network_traffic": "May queue configured IP enrichment.",
    "ttp": "Stores the MITRE ATT&CK ID. Display metadata is resolved when the item is read.",
}
_SERVER_FIELDS = "IDs, authorship, enrichment, nested replies, and other server-managed fields are assigned by the server."


def _target_types(target_kind: EntityType) -> dict:
    try:
        return _TYPES[target_kind]
    except KeyError:
        raise ToolError("target_kind must be alert, case, or task") from None


def _fields(item_type: TimelineItemType) -> set[str]:
    if item_type == "attachment":
        return set(PresignedUploadRequest.model_fields)
    allowed = _COMMON_FIELDS.union(_TYPE_FIELDS[item_type])
    return allowed - {"parent_id", "flagged", "highlighted", "timestamp"} if item_type == "task" else allowed


def _side_effects(item_type: TimelineItemType) -> list[str]:
    if item_type in _ACTOR_TYPES:
        effects = [
            "Links an existing actor by actor_id or finds or creates an actor from the supplied identity.",
            "Records a timeline snapshot.",
        ]
        if item_type == "internal_actor":
            effects.append("May queue configured internal actor enrichment.")
        return effects
    return [_SIDE_EFFECTS[item_type]] if item_type in _SIDE_EFFECTS else []


def _describe_fields(model: type, item_type: TimelineItemType) -> dict:
    schema = model.model_json_schema()
    allowed = _fields(item_type)
    properties = {key: schema["properties"][key] for key in sorted(allowed)}
    properties["description"]["maxLength"] = 16000
    if "parent_id" in properties:
        properties["parent_id"]["description"] = (
            "ID of an existing stored timeline item. A thread may have up to five item levels."
        )
    if item_type == "task":
        properties["title"]["maxLength"] = 200
    if item_type == "threat_actor":
        properties["confidence"].update(minimum=0, maximum=100)
    if item_type in {"alert", "case"}:
        properties[f"{item_type}_id"] = {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": "Numeric or prefixed ID of an existing work item.",
        }
    required = list(schema.get("required", [])) if item_type == "attachment" else list(_REQUIRED_FIELDS.get(item_type, ()))
    fields_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if item_type in _ANY_OF:
        fields_schema["anyOf"] = [{"required": [key]} for key in _ANY_OF[item_type]]
    referenced = {choice["$ref"].rsplit("/", 1)[-1]
                  for prop in properties.values()
                  for choice in prop.get("anyOf", [prop]) if "$ref" in choice}
    if referenced:
        fields_schema["$defs"] = {key: schema["$defs"][key] for key in sorted(referenced)}
    return fields_schema


async def describe_timeline_item(
    target_kind: EntityType,
    item_type: TimelineItemType | None = None,
) -> dict:
    """List supported timeline types or inspect one type's writable fields and examples.

    Args:
        target_kind: Work type whose timeline will receive the item.
        item_type: Specific item type to describe. Omit to list all types for the target.
    """
    supported = _target_types(target_kind)
    if item_type is None:
        return {
            "target_kind": target_kind,
            "item_types": [
                {"item_type": name, "purpose": model.__doc__}
                for name, model in sorted(supported.items())
            ],
        }
    if item_type not in supported:
        raise ToolError(f"{item_type} timeline items cannot be added to {target_kind} timelines")
    model = PresignedUploadRequest if item_type == "attachment" else supported[item_type]
    return {
        "target_kind": target_kind,
        "item_type": item_type,
        "purpose": supported[item_type].__doc__,
        "fields": _describe_fields(model, item_type),
        "example": _EXAMPLES[item_type],
        "side_effects": _side_effects(item_type),
        "guidance": _SERVER_FIELDS,
    }


def _parse_id(value: str, kind: str) -> tuple[int, str]:
    try:
        return parse_entity_id(value, kind)
    except EntityIdParseError as exc:
        raise ToolError(str(exc)) from exc


def _validate_fields(item_type: TimelineItemType, fields: dict) -> None:
    unknown = sorted(fields.keys() - _fields(item_type))
    if unknown:
        raise ToolError(f"Invalid fields for {item_type}: {', '.join(unknown)}. Use describe_timeline_item for writable fields.")
    description = fields.get("description")
    if isinstance(description, str) and len(description) > 16000:
        raise ToolError("Description exceeds 16,000 characters")
    parent_id = fields.get("parent_id")
    if isinstance(parent_id, str) and not parent_id.strip():
        raise ToolError("parent_id must be nonblank")


def _build_item(
    model: type, target_kind: EntityType, item_type: TimelineItemType, item_id: str,
    fields: dict, author: str, created_at: datetime | None,
) -> Any:
    fields = fields.copy()
    ref_key = f"{item_type}_id"
    if item_type in {"alert", "case"} and isinstance(fields.get(ref_key), str):
        fields[ref_key] = _parse_id(fields[ref_key], item_type)[0]
    timestamp = datetime.now(timezone.utc)
    payload = {
        "id": item_id, "type": item_type, "created_at": created_at or timestamp,
        "timestamp": timestamp, "created_by": author, **fields,
    }
    try:
        item = model.model_validate(payload)
        item = _CONVERTERS[target_kind](item.model_dump(mode="json"))
    except ValidationError as exc:
        problems = [
            f"{'.'.join(map(str, error['loc'])) or 'fields'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise ToolError(". ".join(problems)) from exc
    for field in _REQUIRED_FIELDS.get(item_type, ()):
        value = getattr(item, field)
        if value is None or isinstance(value, str) and not value.strip():
            raise ToolError(f"{field} is required for {item_type}")
    choices = _ANY_OF.get(item_type)
    if choices and not any(getattr(item, field) for field in choices):
        raise ToolError(f"{item_type} requires one of {', '.join(choices)}")
    if item_type == "task":
        if len(item.title) > 200:
            raise ToolError("title must be at most 200 characters")
        validate_protected_tag_mutation(None, item.tags)
    if item_type == "threat_actor" and item.confidence is not None and not 0 <= item.confidence <= 100:
        raise ToolError("confidence must be between 0 and 100")
    return item


async def _validate_references(db: AsyncSession, item: Any) -> None:
    if item.type in {"case", "alert"}:
        reference_id = getattr(item, f"{item.type}_id")
        model, _ = _TARGETS[item.type]
        if await db.get(model, reference_id) is None:
            raise ToolError(f"{item.type.capitalize()} {reference_id} not found")
    if item.type in _ACTOR_TYPES and item.actor_id is not None:
        actor = await db.get(Actor, item.actor_id)
        if actor is None or actor.actor_type != _ACTOR_TYPES[item.type]:
            raise ToolError(f"Actor {item.actor_id} is not an existing {item.type}")
    if item.type == "internal_actor" and item.manager_id is not None:
        manager = await db.get(Actor, item.manager_id)
        if manager is None or manager.actor_type != ActorType.INTERNAL:
            raise ToolError(f"Manager {item.manager_id} is not an existing internal actor")


def _committed_output(item: dict, client_item_id: str, *, created: bool) -> dict:
    item_id = item["id"]
    output = _existing_timeline_item_output(item_id, item).model_dump()
    output["item_type"] = item["type"]
    if created:
        output.update(mode="committed", message="Timeline item added successfully")
    if item["type"] == "task":
        task_id = item["task_id"]
        canonical_id = f"linked-task-{task_id}"
        output.update(
            client_item_id=client_item_id,
            item_id=canonical_id,
            task_id=task_id,
            task_human_id=format_entity_id(task_id, TASK_PREFIX),
        )
    return output


async def add_timeline_item(
    target_kind: EntityType,
    target_id: str,
    item_id: str,
    body: str | None = None,
    commit: bool = False,
    created_at: str | None = None,
    migration: bool = False,
    item_type: TimelineItemType = "note",
    fields: dict[str, Any] | None = None,
) -> dict:
    """Preview or add a typed timeline item. Use describe_timeline_item to find writable fields.

    Legacy notes may pass body alone. With fields, body is shorthand for description.
    Supply commit=true to write as the authenticated analyst. Reuse item_id when retrying.

    Args:
        target_kind: Work type whose timeline will receive the item.
        target_id: Numeric or prefixed ID of the owning alert, case, or task.
        item_id: Client-generated ID scoped to the owning timeline. Reuse it on retries.
        body: Shorthand for fields.description. Legacy note calls may omit fields.
        commit: Preview with false or write as the authenticated analyst with true.
        created_at: Migration-only creation timestamp in ISO-8601 with a timezone.
        migration: Request a timestamp override using an authorized NHI account.
        item_type: Timeline item type. Defaults to note.
        fields: Writable item fields. Discover the schema with describe_timeline_item.
    """
    supported = _target_types(target_kind)
    if item_type not in supported:
        raise ToolError(f"{item_type} timeline items cannot be added to {target_kind} timelines")
    if not item_id.strip():
        raise ToolError("item_id must be nonblank")
    if created_at is not None:
        try:
            parsed_created_at = datetime.fromisoformat(created_at)
        except ValueError as exc:
            raise ToolError("created_at must be a valid ISO-8601 datetime") from exc
        if parsed_created_at.tzinfo is None:
            raise ToolError("created_at must include timezone information")
    else:
        parsed_created_at = None

    try:
        user = (
            _require_mcp_non_auditor_user_object()
            if commit or migration or created_at is not None else _get_authenticated_user()
        )
        created_at_override = normalize_created_at_override(
            current_user=user, migration=migration, created_at=parsed_created_at,
        )
        if item_type == "note" and body is not None and fields is None:
            return await add_timeline_item_tool(
                target_kind, target_id, item_id, body, commit, created_at, migration,
            )
        fields = dict(fields or {})
        if body is not None:
            if "description" in fields:
                raise ToolError("Supply either body or fields.description")
            fields["description"] = body
        _validate_fields(item_type, fields)
        if item_type == "attachment":
            from app.mcp.attachment_tools import add_timeline_attachment

            return await add_timeline_attachment(
                target_kind=target_kind, target_id=target_id, item_id=item_id,
                fields=fields, commit=commit, created_at_override=created_at_override,
            )
        return await _author_item(
            target_kind=target_kind, target_id=target_id, item_id=item_id, item_type=item_type,
            fields=fields, commit=commit, user=user, created_at=created_at_override,
        )
    except HTTPException as exc:
        raise ToolError(exc.detail) from exc
    except (TimelineItemConflict, TimelineValidationError, ProtectedTagMutationError) as exc:
        raise ToolError(str(exc)) from exc


async def _author_item(
    *, target_kind: EntityType, target_id: str, item_id: str, item_type: TimelineItemType,
    fields: dict, commit: bool, user: Any, created_at: datetime | None,
) -> dict:
    model, _ = _TARGETS[target_kind]
    entity_id, prefix = _parse_id(target_id, target_kind)
    canonical_target_id = format_entity_id(entity_id, prefix)
    not_found = f"{target_kind.capitalize()} {canonical_target_id} not found"
    author = _get_authenticated_username()
    item = _build_item(_TYPES[target_kind][item_type], target_kind, item_type, item_id, fields, author, created_at)
    async with async_session_factory() as db:
        row = (await db.execute(select(model.timeline_items).where(model.id == entity_id))).first()
        if row is None:
            raise ToolError(not_found)
        timeline = row[0] or {}
        await _validate_references(db, item)
        if not commit:
            retry = await find_timeline_authoring_retry(
                db,
                timeline_items=timeline,
                entity_type=target_kind,
                entity_id=entity_id,
                client_item_id=item_id,
                item_type=item_type,
                owner_id=getattr(user, "id", None),
            )
            if retry is not None:
                return _committed_output(retry, item_id, created=False)
            existing = timeline_service.find_item_by_id(timeline, item_id)
            if existing is not None:
                if existing.get("type") != item_type:
                    raise ToolError(f"Timeline item ID {item_id} already belongs to another item type")
                return _committed_output(existing, item_id, created=False)
            if item.parent_id is not None:
                timeline_service.validate_reply_parent(timeline, item.parent_id)
            return {
                "mode": "dry_run",
                "item_id": item_id,
                "item_type": item_type,
                "created_at": created_at,
                "author": author,
                "target_kind": target_kind,
                "target_id": canonical_target_id,
                "fields": item.model_dump(mode="json", include=set(fields)),
                "side_effects": _side_effects(item_type),
                "message": "Dry-run preview. Set commit=true to apply.",
            }
        result = await add_timeline_item_and_commit(
            db,
            entity_id=entity_id,
            entity_type=target_kind,
            timeline_item=item,
            performed_by=author,
            created_at_override=created_at,
            preserve_item_id=True,
            idempotent=True,
            retry_client_item_id=item_id,
            retry_user_id=user.id if item_type == "task" else None,
            require_parent=True,
        )
        if result is None:
            raise ToolError(not_found)
        return _committed_output(result.item, item_id, created=result.created)
