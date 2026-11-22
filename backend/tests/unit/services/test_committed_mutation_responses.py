from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import langflow as langflow_routes
from app.api.routes import link_templates as link_template_routes
from app.models.enums import SessionStatus, UserRole, UserStatus
from app.models.models import (
    ContextEntry,
    ContextEntryCreate,
    LangFlowSession,
    LangFlowSessionUpdate,
    LinkTemplate,
    LinkTemplateUpdate,
    UserAccount,
)
from app.services import admin_auth_service as admin_auth_module
from app.services import alert_service as alert_module
from app.services import case_service as case_module
from app.services import context_service as context_module
from app.services import task_service as task_module
from app.services.admin_auth_service import AdminAuthService
from app.services.context_service import ContextService


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        return self._value


class _AuditService:
    async def log_event(self, **_kwargs: Any) -> None:
        pass

    async def user_updated(self, **_kwargs: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_context_create_serializes_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(entry=None, committed=False, refresh_called=False)

    def add(instance: object) -> None:
        if isinstance(instance, ContextEntry):
            state.entry = instance

    async def flush() -> None:
        state.entry.id = 23

    async def commit() -> None:
        state.committed = True

    async def refresh(_instance: object) -> None:
        state.refresh_called = True
        raise AssertionError("post-commit refresh")

    db = SimpleNamespace(add=add, flush=flush, commit=commit, refresh=refresh, execute=AsyncMock())
    monkeypatch.setattr(context_module, "get_audit_service", lambda _db: _AuditService())

    result = await ContextService(cast(AsyncSession, db)).create_entry(
        ContextEntryCreate(
            body="Known-safe context",
            criteria=[],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ),
        author="analyst",
    )

    assert result.id == 23
    assert result.body == "Known-safe context"
    assert state.committed is True
    assert state.refresh_called is False


@pytest.mark.asyncio
async def test_admin_update_does_not_rehydrate_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = uuid4()
    user = UserAccount(
        username="analyst",
        email="analyst@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    state = SimpleNamespace(committed=False, refresh_called=False)

    async def execute(_statement: object) -> _ScalarResult:
        return _ScalarResult(user)

    async def commit() -> None:
        state.committed = True

    async def refresh(_instance: object) -> None:
        state.refresh_called = True
        raise AssertionError("post-commit refresh")

    db = SimpleNamespace(execute=execute, commit=commit, refresh=refresh)
    monkeypatch.setattr(admin_auth_module, "get_audit_service", lambda _db: _AuditService())
    monkeypatch.setattr(
        admin_auth_module.oidc_local_credential_policy,
        "revoke_impermissible_credentials",
        AsyncMock(),
    )

    result = await AdminAuthService(password_hasher=SimpleNamespace()).update_user(
        admin_user_id=admin_id,
        target_user_id=user.id,
        description="Detection engineer",
        request_metadata=SimpleNamespace(),
        db=cast(AsyncSession, db),
    )

    assert result.description == "Detection engineer"
    assert state.committed is True
    assert state.refresh_called is False


@pytest.mark.asyncio
async def test_langflow_update_counts_messages_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = LangFlowSession(
        flow_id="flow-1",
        user_id=user_id,
        status=SessionStatus.ACTIVE,
    )
    state = SimpleNamespace(committed=False, refresh_called=False)

    async def execute(_statement: object) -> _ScalarResult:
        if state.committed:
            raise AssertionError("post-commit query")
        return _ScalarResult(4)

    async def commit() -> None:
        state.committed = True

    async def refresh(_instance: object) -> None:
        state.refresh_called = True
        raise AssertionError("post-commit refresh")

    db = SimpleNamespace(execute=execute, commit=commit, refresh=refresh)
    monkeypatch.setattr(
        langflow_routes,
        "verify_session_access",
        AsyncMock(return_value=session),
    )

    result = await langflow_routes.update_session(
        session_id=session.id,
        session_update=LangFlowSessionUpdate(title="Updated chat"),
        db=cast(AsyncSession, db),
        current_user=SimpleNamespace(id=user_id),
    )

    assert result.title == "Updated chat"
    assert result.message_count == 4
    assert state.committed is True
    assert state.refresh_called is False


@pytest.mark.asyncio
async def test_link_template_update_serializes_before_commit() -> None:
    template = LinkTemplate(
        id=31,
        template_id="case-console",
        name="Case Console",
        icon_name="Link2",
        tooltip_template="Open {{human_id}}",
        url_template="https://console.example/cases/{{human_id}}",
    )
    state = SimpleNamespace(committed=False, refresh_called=False)

    async def get(_model: type[object], _entity_id: int) -> LinkTemplate:
        return template

    async def commit() -> None:
        state.committed = True

    async def refresh(_instance: object) -> None:
        state.refresh_called = True
        raise AssertionError("post-commit refresh")

    db = SimpleNamespace(get=get, commit=commit, refresh=refresh)

    result = await link_template_routes.update_link_template(
        template_id=31,
        template_data=LinkTemplateUpdate(name="Updated Console"),
        db=cast(AsyncSession, db),
        _=SimpleNamespace(),
    )

    assert result.name == "Updated Console"
    assert state.committed is True
    assert state.refresh_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "entity_type", "response_loader"),
    [
        (alert_module, "alert", "get_alert"),
        (case_module, "case", "_load_timeline_mutation_response"),
        (task_module, "task", "get_task"),
    ],
)
@pytest.mark.parametrize("commit_failed", [True, False], ids=["commit-failed", "reload-failed"])
async def test_timeline_removal_recovers_on_the_correct_side_of_commit(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    entity_type: str,
    response_loader: str,
    commit_failed: bool,
) -> None:
    service = getattr(module, f"{entity_type}_service")
    timeline = {"note-1": {"id": "note-1", "type": "note"}}
    fallback = SimpleNamespace(id=5, timeline_items=timeline)
    db = AsyncMock(spec=AsyncSession)
    calls = Mock()
    calls.attach_mock(db.commit, "commit")
    calls.attach_mock(db.expunge_all, "detach")
    calls.attach_mock(db.rollback, "rollback")
    reload = AsyncMock(side_effect=RuntimeError("response reload failed"))
    calls.attach_mock(reload, "reload")

    async def remove_and_commit(
        session: AsyncSession, *, item_id: str, **_kwargs: Any
    ) -> dict[str, Any]:
        removed_item = timeline.pop(item_id)
        await session.commit()
        return removed_item

    monkeypatch.setattr(service, f"_get_{entity_type}_model", AsyncMock(return_value=fallback))
    monkeypatch.setattr(module, "remove_timeline_item_and_commit", remove_and_commit)
    monkeypatch.setattr(service, response_loader, reload)

    if commit_failed:
        db.commit.side_effect = RuntimeError("commit failed")
        with pytest.raises(RuntimeError, match="commit failed"):
            await service.remove_timeline_item(db, 5, "note-1", "analyst")
        assert calls.mock_calls == [call.commit(), call.rollback()]
    else:
        result = await service.remove_timeline_item(db, 5, "note-1", "analyst")
        assert result is fallback
        assert result.timeline_items == {}
        assert calls.mock_calls == [call.commit(), call.detach(), call.reload(db, 5), call.rollback()]
    db.rollback.assert_awaited_once_with()
