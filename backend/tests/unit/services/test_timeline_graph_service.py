from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TimelineGraph, TimelineGraphOperation, TimelineGraphPatch
from app.services.timeline_graph_service import TimelineGraphService


class _NestedTransaction:
    def __init__(self, session: _GraphInsertRaceSession) -> None:
        self._session = session

    async def __aenter__(self) -> None:
        self._session.savepoint_started = True

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> bool:
        if exc_type is not None:
            self._session.graph_pending = False
            self._session.savepoint_rolled_back = True
        return False


class _GraphInsertRaceSession:
    """Minimal transaction model for a graph-row uniqueness race."""

    def __init__(self) -> None:
        self.unrelated_pending = True
        self.unrelated_survived = False
        self.graph_pending = False
        self.savepoint_started = False
        self.savepoint_rolled_back = False
        self.outer_rolled_back = False
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1
        if self.unrelated_pending:
            self.unrelated_pending = False
            self.unrelated_survived = True
        if self.graph_pending:
            raise IntegrityError("INSERT INTO timeline_graphs", {}, Exception("duplicate"))

    def begin_nested(self) -> _NestedTransaction:
        return _NestedTransaction(self)

    def add(self, _: TimelineGraph) -> None:
        self.graph_pending = True

    async def rollback(self) -> None:
        self.outer_rolled_back = True
        self.unrelated_survived = False


@pytest.mark.asyncio
async def test_graph_insert_race_preserves_unrelated_pending_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TimelineGraphService()
    db = _GraphInsertRaceSession()
    existing_row = TimelineGraph(
        entity_type="case",
        entity_id=42,
        created_by="race-winner",
        updated_by="race-winner",
    )
    rows = iter([None, existing_row])

    async def get_graph_row(*_: Any, **__: Any) -> TimelineGraph | None:
        return next(rows)

    monkeypatch.setattr(service, "_get_graph_row", get_graph_row)

    result = await service._get_or_create_graph_row(
        cast(AsyncSession, db),
        "case",
        42,
        "race-loser",
    )

    assert result is existing_row
    assert db.flush_count == 2
    assert db.savepoint_started is True
    assert db.savepoint_rolled_back is True
    assert db.outer_rolled_back is False
    assert db.unrelated_survived is True


@pytest.mark.asyncio
async def test_empty_patch_does_not_update_existing_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TimelineGraphService()
    updated_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    row = TimelineGraph(
        entity_type="case",
        entity_id=42,
        graph={"nodes": {"node-1": {"id": "node-1"}}, "edges": {}},
        revision=7,
        updated_at=updated_at,
        created_by="creator",
        updated_by="previous-user",
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    ensure_entity_exists = AsyncMock()
    get_graph_row = AsyncMock(return_value=row)
    get_or_create_graph_row = AsyncMock()
    emit_event = AsyncMock()
    monkeypatch.setattr(service, "_ensure_entity_exists", ensure_entity_exists)
    monkeypatch.setattr(service, "_get_graph_row", get_graph_row)
    monkeypatch.setattr(service, "_get_or_create_graph_row", get_or_create_graph_row)
    monkeypatch.setattr("app.services.timeline_graph_service.emit_event", emit_event)

    result = await service.patch_graph(
        cast(AsyncSession, db),
        "case",
        42,
        TimelineGraphPatch(base_revision=0, operations=[]),
        "current-user",
    )

    assert result.revision == 7
    assert result.updated_at == updated_at
    assert result.updated_by == "previous-user"
    get_graph_row.assert_awaited_once_with(db, "case", 42, for_update=False)
    get_or_create_graph_row.assert_not_awaited()
    emit_event.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_patch_does_not_create_graph_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TimelineGraphService()
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    get_graph_row = AsyncMock(return_value=None)
    get_or_create_graph_row = AsyncMock()
    emit_event = AsyncMock()
    monkeypatch.setattr(service, "_ensure_entity_exists", AsyncMock())
    monkeypatch.setattr(service, "_get_graph_row", get_graph_row)
    monkeypatch.setattr(service, "_get_or_create_graph_row", get_or_create_graph_row)
    monkeypatch.setattr("app.services.timeline_graph_service.emit_event", emit_event)

    result = await service.patch_graph(
        cast(AsyncSession, db),
        "task",
        84,
        TimelineGraphPatch(base_revision=0, operations=[]),
        "current-user",
    )

    assert result.revision == 0
    assert result.graph.nodes == {}
    assert result.graph.edges == {}
    get_or_create_graph_row.assert_not_awaited()
    emit_event.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_nonempty_patch_builds_response_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TimelineGraphService()
    row = TimelineGraph(
        entity_type="case",
        entity_id=42,
        created_by="creator",
        updated_by="creator",
    )
    db = SimpleNamespace(
        commit=AsyncMock(),
        refresh=AsyncMock(side_effect=AssertionError("post-commit refresh")),
    )
    monkeypatch.setattr(service, "_ensure_entity_exists", AsyncMock())
    monkeypatch.setattr(service, "_get_or_create_graph_row", AsyncMock(return_value=row))
    monkeypatch.setattr("app.services.timeline_graph_service.emit_event", AsyncMock())

    result = await service.patch_graph(
        cast(AsyncSession, db),
        "case",
        42,
        TimelineGraphPatch(
            base_revision=0,
            operations=[
                TimelineGraphOperation(
                    type="add_group",
                    node_id="group-1",
                    label="Evidence",
                    position={"x": 1, "y": 2},
                )
            ],
        ),
        "analyst",
    )

    assert result.revision == 1
    assert result.graph.nodes["group-1"]["label"] == "Evidence"
    db.commit.assert_awaited_once_with()
    db.refresh.assert_not_awaited()


def test_apply_operation_dispatches_node_and_edge_lifecycles() -> None:
    service = TimelineGraphService()
    graph: dict[str, dict[str, dict[str, Any]]] = {"nodes": {}, "edges": {}}
    meta: dict[str, dict[str, int]] = {
        "nodes": {},
        "edges": {},
        "deleted_nodes": {},
        "deleted_edges": {},
    }

    operations = [
        TimelineGraphOperation(
            type="add_group",
            node_id="group-1",
            label=" Evidence ",
            position={"x": 1, "y": 2},
        ),
        TimelineGraphOperation(
            type="add_node",
            node_id="node-1",
            item_id="item-1",
            parent_node_id="group-1",
            position={"x": 3, "y": 4},
        ),
        TimelineGraphOperation(
            type="add_node",
            node_id="node-2",
            item_id="item-2",
            position={"x": 5, "y": 6},
        ),
        TimelineGraphOperation(
            type="add_edge",
            edge_id="edge-1",
            source="node-1",
            target="node-2",
            marker="forward",
        ),
        TimelineGraphOperation(
            type="reconnect_edge",
            edge_id="edge-1",
            source="node-2",
            target="node-1",
        ),
        TimelineGraphOperation(
            type="update_edge_label",
            edge_id="edge-1",
            label=" related ",
        ),
        TimelineGraphOperation(
            type="update_edge_metadata",
            edge_id="edge-1",
            marker="bidirectional",
        ),
        TimelineGraphOperation(type="remove_node", node_id="node-1"),
    ]

    for revision, operation in enumerate(operations, start=1):
        service._apply_operation(graph, meta, revision, operation)

    assert graph["nodes"]["group-1"]["label"] == "Evidence"
    assert "node-1" not in graph["nodes"]
    assert "edge-1" not in graph["edges"]
    assert meta["deleted_nodes"]["node-1"] == 8
    assert meta["deleted_edges"]["edge-1"] == 8
