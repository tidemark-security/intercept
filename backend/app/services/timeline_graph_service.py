from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.enums import RealtimeEventType
from app.models.models import (
    Case,
    Task,
    TimelineGraph,
    TimelineGraphConflictRead,
    TimelineGraphDocument,
    TimelineGraphOperation,
    TimelineGraphPatch,
    TimelineGraphRead,
)
from app.services.realtime_service import emit_event


EMPTY_GRAPH: Dict[str, Dict[str, Dict[str, Any]]] = {"nodes": {}, "edges": {}}
EMPTY_META: Dict[str, Dict[str, int]] = {
    "nodes": {},
    "edges": {},
    "deleted_nodes": {},
    "deleted_edges": {},
}


class TimelineGraphConflict(Exception):
    def __init__(self, conflict: TimelineGraphConflictRead) -> None:
        self.conflict = conflict


def _empty_graph() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {"nodes": {}, "edges": {}}


def _empty_meta() -> Dict[str, Dict[str, int]]:
    return {"nodes": {}, "edges": {}, "deleted_nodes": {}, "deleted_edges": {}}


def _normalize_graph(value: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not isinstance(value, dict):
        return _empty_graph()
    nodes = value.get("nodes") if isinstance(value.get("nodes"), dict) else {}
    edges = value.get("edges") if isinstance(value.get("edges"), dict) else {}
    return {"nodes": deepcopy(nodes), "edges": deepcopy(edges)}


def _normalize_meta(value: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    meta = _empty_meta()
    if not isinstance(value, dict):
        return meta
    for key in meta:
        raw_bucket = value.get(key)
        if isinstance(raw_bucket, dict):
            meta[key] = {
                str(object_id): int(revision)
                for object_id, revision in raw_bucket.items()
                if isinstance(revision, int)
            }
    return meta


def _read_from_row(row: Optional[TimelineGraph], entity_type: str, entity_id: int) -> TimelineGraphRead:
    if row is None:
        return TimelineGraphRead(
            entity_type=entity_type,  # type: ignore[arg-type]
            entity_id=entity_id,
            graph=TimelineGraphDocument(),
            revision=0,
        )
    return TimelineGraphRead(
        entity_type=row.entity_type,  # type: ignore[arg-type]
        entity_id=row.entity_id,
        graph=TimelineGraphDocument(**_normalize_graph(row.graph)),
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def _object_changed_after(meta: Dict[str, Dict[str, int]], bucket: str, object_id: str, base_revision: int) -> bool:
    return meta.get(bucket, {}).get(object_id, -1) > base_revision


def _validate_position(operation: TimelineGraphOperation) -> Dict[str, float]:
    if operation.position is None:
        raise ValueError(f"{operation.type} requires position")
    x = operation.position.get("x")
    y = operation.position.get("y")
    if x is None or y is None:
        raise ValueError(f"{operation.type} requires position.x and position.y")
    return {"x": float(x), "y": float(y)}


def _validate_size(operation: TimelineGraphOperation) -> Dict[str, float]:
    if operation.width is None or operation.height is None:
        raise ValueError(f"{operation.type} requires width and height")
    width = float(operation.width)
    height = float(operation.height)
    if width <= 0 or height <= 0:
        raise ValueError(f"{operation.type} requires positive width and height")
    return {"width": width, "height": height}


def _require_node_id(operation: TimelineGraphOperation) -> str:
    if not operation.node_id:
        raise ValueError(f"{operation.type} requires node_id")
    return operation.node_id


def _require_edge_id(operation: TimelineGraphOperation) -> str:
    if not operation.edge_id:
        raise ValueError(f"{operation.type} requires edge_id")
    return operation.edge_id


class TimelineGraphService:
    async def get_graph(self, db: AsyncSession, entity_type: str, entity_id: int) -> TimelineGraphRead:
        await self._ensure_entity_exists(db, entity_type, entity_id)
        row = await self._get_graph_row(db, entity_type, entity_id, for_update=False)
        return _read_from_row(row, entity_type, entity_id)

    async def patch_graph(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        patch: TimelineGraphPatch,
        updated_by: str,
    ) -> TimelineGraphRead:
        await self._ensure_entity_exists(db, entity_type, entity_id)
        row = await self._get_or_create_graph_row(db, entity_type, entity_id, updated_by)
        graph = _normalize_graph(row.graph)
        meta = _normalize_meta(row.graph_meta)
        base_revision = patch.base_revision

        conflicting_indexes = self._find_conflicts(graph, meta, base_revision, patch.operations)
        if conflicting_indexes:
            raise TimelineGraphConflict(
                TimelineGraphConflictRead(
                    graph=_read_from_row(row, entity_type, entity_id),
                    conflicting_operation_indexes=conflicting_indexes,
                )
            )

        for operation in patch.operations:
            self._apply_operation(graph, meta, row.revision + 1, operation)

        row.revision += 1
        row.graph = graph
        row.graph_meta = meta
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = updated_by

        await emit_event(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=RealtimeEventType.TIMELINE_GRAPH_UPDATED,
            performed_by=updated_by,
        )
        await db.commit()
        await db.refresh(row)
        return _read_from_row(row, entity_type, entity_id)

    async def _ensure_entity_exists(self, db: AsyncSession, entity_type: str, entity_id: int) -> None:
        if entity_type == "case":
            entity = await db.get(Case, entity_id)
        elif entity_type == "task":
            entity = await db.get(Task, entity_id)
        else:
            raise ValueError("Timeline graphs are only supported for cases and tasks")
        if entity is None:
            raise LookupError(f"{entity_type.title()} not found")

    async def _get_graph_row(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        *,
        for_update: bool,
    ) -> Optional[TimelineGraph]:
        query = select(TimelineGraph).where(
            col(TimelineGraph.entity_type) == entity_type,
            col(TimelineGraph.entity_id) == entity_id,
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _get_or_create_graph_row(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        username: str,
    ) -> TimelineGraph:
        row = await self._get_graph_row(db, entity_type, entity_id, for_update=True)
        if row is not None:
            return row

        now = datetime.now(timezone.utc)
        row = TimelineGraph(
            entity_type=entity_type,
            entity_id=entity_id,
            graph=_empty_graph(),
            graph_meta=_empty_meta(),
            revision=0,
            created_at=now,
            updated_at=now,
            created_by=username,
            updated_by=username,
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            row = await self._get_graph_row(db, entity_type, entity_id, for_update=True)
            if row is None:
                raise
        return row

    def _find_conflicts(
        self,
        graph: Dict[str, Dict[str, Dict[str, Any]]],
        meta: Dict[str, Dict[str, int]],
        base_revision: int,
        operations: List[TimelineGraphOperation],
    ) -> List[int]:
        conflicts: List[int] = []
        for index, operation in enumerate(operations):
            if operation.type in {"add_node", "add_group", "move_node"}:
                continue
            if operation.type in {"resize_node", "update_node_metadata"}:
                node_id = _require_node_id(operation)
                if node_id not in graph["nodes"] or _object_changed_after(meta, "nodes", node_id, base_revision):
                    conflicts.append(index)
                continue
            if operation.type == "remove_node":
                node_id = _require_node_id(operation)
                if _object_changed_after(meta, "nodes", node_id, base_revision):
                    conflicts.append(index)
                    continue
                incident_edges = [
                    edge_id for edge_id, edge in graph["edges"].items()
                    if edge.get("source") == node_id or edge.get("target") == node_id
                ]
                if any(_object_changed_after(meta, "edges", edge_id, base_revision) for edge_id in incident_edges):
                    conflicts.append(index)
                continue
            if operation.type == "add_edge":
                edge_id = _require_edge_id(operation)
                if _object_changed_after(meta, "edges", edge_id, base_revision):
                    conflicts.append(index)
                continue
            if operation.type == "remove_edge":
                continue
            if operation.type in {"update_edge_label", "update_edge_metadata", "reconnect_edge"}:
                edge_id = _require_edge_id(operation)
                if edge_id not in graph["edges"] or _object_changed_after(meta, "edges", edge_id, base_revision):
                    conflicts.append(index)
        return conflicts

    def _apply_operation(
        self,
        graph: Dict[str, Dict[str, Dict[str, Any]]],
        meta: Dict[str, Dict[str, int]],
        next_revision: int,
        operation: TimelineGraphOperation,
    ) -> None:
        if operation.type == "add_node":
            node_id = _require_node_id(operation)
            if not operation.item_id:
                raise ValueError("add_node requires item_id")
            graph["nodes"][node_id] = {
                "id": node_id,
                "item_id": operation.item_id,
                "position": _validate_position(operation),
            }
            if operation.width is not None and operation.height is not None:
                graph["nodes"][node_id].update(_validate_size(operation))
            if "parent_node_id" in operation.model_fields_set:
                graph["nodes"][node_id]["parent_node_id"] = operation.parent_node_id
            meta["nodes"][node_id] = next_revision
            meta["deleted_nodes"].pop(node_id, None)
            return

        if operation.type == "add_group":
            node_id = _require_node_id(operation)
            graph["nodes"][node_id] = {
                "id": node_id,
                "kind": "group",
                "label": operation.label.strip() if operation.label else "Group",
                "position": _validate_position(operation),
            }
            if operation.width is not None and operation.height is not None:
                graph["nodes"][node_id].update(_validate_size(operation))
            meta["nodes"][node_id] = next_revision
            meta["deleted_nodes"].pop(node_id, None)
            return

        if operation.type == "move_node":
            node_id = _require_node_id(operation)
            if node_id in graph["nodes"]:
                graph["nodes"][node_id]["position"] = _validate_position(operation)
                meta["nodes"][node_id] = next_revision
            return

        if operation.type == "resize_node":
            node_id = _require_node_id(operation)
            if node_id in graph["nodes"]:
                graph["nodes"][node_id].update(_validate_size(operation))
                meta["nodes"][node_id] = next_revision
            return

        if operation.type == "update_node_metadata":
            node_id = _require_node_id(operation)
            if node_id in graph["nodes"]:
                if "parent_node_id" in operation.model_fields_set:
                    graph["nodes"][node_id]["parent_node_id"] = operation.parent_node_id
                if "label" in operation.model_fields_set and graph["nodes"][node_id].get("kind") == "group":
                    graph["nodes"][node_id]["label"] = operation.label.strip() if operation.label else "Group"
                meta["nodes"][node_id] = next_revision
            return

        if operation.type == "remove_node":
            node_id = _require_node_id(operation)
            if graph["nodes"].pop(node_id, None) is not None:
                meta["nodes"].pop(node_id, None)
                meta["deleted_nodes"][node_id] = next_revision
            for child_node in graph["nodes"].values():
                if child_node.get("parent_node_id") == node_id:
                    child_node["parent_node_id"] = None
            for edge_id, edge in list(graph["edges"].items()):
                if edge.get("source") == node_id or edge.get("target") == node_id:
                    graph["edges"].pop(edge_id, None)
                    meta["edges"].pop(edge_id, None)
                    meta["deleted_edges"][edge_id] = next_revision
            return

        if operation.type == "add_edge":
            edge_id = _require_edge_id(operation)
            if not operation.source or not operation.target:
                raise ValueError("add_edge requires source and target")
            graph["edges"][edge_id] = {
                "id": edge_id,
                "source": operation.source,
                "target": operation.target,
                "source_handle": operation.source_handle,
                "target_handle": operation.target_handle,
                "label": operation.label,
            }
            if operation.marker is not None:
                graph["edges"][edge_id]["marker"] = operation.marker
            meta["edges"][edge_id] = next_revision
            meta["deleted_edges"].pop(edge_id, None)
            return

        if operation.type == "reconnect_edge":
            edge_id = _require_edge_id(operation)
            if edge_id in graph["edges"]:
                if not operation.source or not operation.target:
                    raise ValueError("reconnect_edge requires source and target")
                graph["edges"][edge_id].update({
                    "source": operation.source,
                    "target": operation.target,
                    "source_handle": operation.source_handle,
                    "target_handle": operation.target_handle,
                })
                meta["edges"][edge_id] = next_revision
            return

        if operation.type == "remove_edge":
            edge_id = _require_edge_id(operation)
            if graph["edges"].pop(edge_id, None) is not None:
                meta["edges"].pop(edge_id, None)
                meta["deleted_edges"][edge_id] = next_revision
            return

        if operation.type == "update_edge_label":
            edge_id = _require_edge_id(operation)
            if edge_id in graph["edges"]:
                label = operation.label.strip() if operation.label else None
                graph["edges"][edge_id]["label"] = label or None
                meta["edges"][edge_id] = next_revision

        if operation.type == "update_edge_metadata":
            edge_id = _require_edge_id(operation)
            if edge_id in graph["edges"]:
                if "marker" in operation.model_fields_set:
                    graph["edges"][edge_id]["marker"] = operation.marker
                meta["edges"][edge_id] = next_revision


timeline_graph_service = TimelineGraphService()