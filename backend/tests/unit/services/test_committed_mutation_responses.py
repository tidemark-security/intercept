from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
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
from app.services import context_service as context_module
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

    db = SimpleNamespace(add=add, flush=flush, commit=commit, refresh=refresh)
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
