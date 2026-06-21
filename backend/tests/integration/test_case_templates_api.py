from __future__ import annotations

from typing import Any, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import PICERLStage, Priority, UserRole
from app.models.models import AuditLog, Case, Task, UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login(
    client: AsyncClient,
    session_maker: Any,
    user_factory: Callable[..., UserAccount],
    *,
    username: str,
) -> str:
    user = user_factory(username=username)
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200
    cookie = response.cookies.get("intercept_session")
    assert cookie is not None
    return cookie


@pytest.mark.asyncio
async def test_case_template_management_defaults_filters_and_admin_writes(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin_cookie = await _login(client, session_maker, admin_user_factory, username="template-admin")
    analyst_cookie = await _login(client, session_maker, analyst_user_factory, username="template-analyst")

    create_response = await client.post(
        "/api/v1/case-templates",
        cookies={"intercept_session": admin_cookie},
        json={
            "title": "DLP Exfiltration",
            "description": "Response steps for suspected data loss",
            "case_tags": [" dlp ", "DLP", "exfiltration"],
            "template_tasks": [
                {
                    "title": "Collect evidence",
                    "description": "Gather alert and user context",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                    "relative_due_seconds": 3600,
                    "tags": ["evidence"],
                }
            ],
        },
    )
    assert create_response.status_code == 200
    template = create_response.json()
    assert template["status"] == "DRAFT"
    assert template["human_id"].startswith("TPL-")
    assert template["case_tags"] == ["dlp", "exfiltration"]

    default_list = await client.get(
        "/api/v1/case-templates",
        cookies={"intercept_session": analyst_cookie},
    )
    assert default_list.status_code == 200
    assert default_list.json()["items"] == []

    publish_response = await client.post(
        f"/api/v1/case-templates/{template['id']}/publish",
        cookies={"intercept_session": admin_cookie},
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "PUBLISHED"

    published_list = await client.get(
        "/api/v1/case-templates",
        cookies={"intercept_session": analyst_cookie},
    )
    assert published_list.status_code == 200
    assert [item["title"] for item in published_list.json()["items"]] == ["DLP Exfiltration"]

    duplicate_response = await client.post(
        "/api/v1/case-templates",
        cookies={"intercept_session": admin_cookie},
        json={"title": " dlp   exfiltration ", "description": "Duplicate"},
    )
    assert duplicate_response.status_code == 400
    assert "unique" in duplicate_response.json()["detail"]

    analyst_write = await client.post(
        "/api/v1/case-templates",
        cookies={"intercept_session": analyst_cookie},
        json={"title": "Analyst draft"},
    )
    assert analyst_write.status_code == 403


@pytest.mark.asyncio
async def test_apply_published_template_creates_real_tasks_tags_and_audit_note(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin_cookie = await _login(client, session_maker, admin_user_factory, username="template-admin-apply")
    analyst_cookie = await _login(client, session_maker, analyst_user_factory, username="template-analyst-apply")

    create_response = await client.post(
        "/api/v1/case-templates",
        cookies={"intercept_session": admin_cookie},
        json={
            "title": "Credential Theft Response",
            "description": "Response steps for credential theft",
            "status": "PUBLISHED",
            "case_tags": ["credential-theft"],
            "template_tasks": [
                {
                    "title": "Collect identity logs",
                    "picerl_stage": PICERLStage.IDENTIFICATION.value,
                    "relative_due_seconds": 7200,
                },
                {
                    "title": "Reset credentials",
                    "picerl_stage": PICERLStage.CONTAINMENT.value,
                    "priority": Priority.HIGH.value,
                    "tags": ["containment"],
                },
            ],
        },
    )
    assert create_response.status_code == 200
    template_id = create_response.json()["id"]

    async with session_maker() as session:
        case = Case(
            title="Credential theft alert",
            description="Seeded case",
            priority=Priority.CRITICAL,
            created_by="seed",
            tags=["existing"],
        )
        session.add(case)
        await session.commit()
        assert case.id is not None
        case_id = case.id

    apply_response = await client.post(
        f"/api/v1/case-templates/cases/{case_id}/apply/{template_id}",
        cookies={"intercept_session": analyst_cookie},
        json={
            "task_overrides": [
                {"index": 1, "assignee": "ir-lead"},
            ]
        },
    )
    assert apply_response.status_code == 200
    payload = apply_response.json()
    assert len(payload["created_task_ids"]) == 2
    assert payload["skipped_task_titles"] == []

    async with session_maker() as session:
        tasks = (
            await session.execute(
                select(Task).where(Task.case_id == case_id).order_by(Task.linked_at.asc())
            )
        ).scalars().all()
        assert [task.title for task in tasks] == ["Collect identity logs", "Reset credentials"]
        assert tasks[0].source_tpl == template_id
        assert tasks[0].picerl_stage == PICERLStage.IDENTIFICATION
        assert tasks[0].priority == Priority.CRITICAL
        assert tasks[0].assignee is None
        assert tasks[1].priority == Priority.HIGH
        assert tasks[1].assignee == "ir-lead"
        assert tasks[1].tags == ["containment"]
        assert tasks[0].linked_at < tasks[1].linked_at

        refreshed_case = await session.get(Case, case_id)
        assert refreshed_case is not None
        assert refreshed_case.tags == ["existing", "credential-theft"]
        notes = [
            item
            for item in (refreshed_case.timeline_items or {}).values()
            if item.get("type") == "note"
        ]
        assert any("Applied Case Template" in note.get("description", "") for note in notes)

        audit_events = (
            await session.execute(
                select(AuditLog.event_type).where(AuditLog.entity_type == "case_template")
            )
        ).scalars().all()
        assert "case_template.created" in audit_events


@pytest.mark.asyncio
async def test_apply_rejects_draft_templates_and_no_selected_tasks(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin_cookie = await _login(client, session_maker, admin_user_factory, username="template-admin-reject")
    analyst_cookie = await _login(client, session_maker, analyst_user_factory, username="template-analyst-reject")

    create_response = await client.post(
        "/api/v1/case-templates",
        cookies={"intercept_session": admin_cookie},
        json={
            "title": "Draft Template",
            "template_tasks": [
                {"title": "Draft task", "picerl_stage": PICERLStage.PREPARATION.value}
            ],
        },
    )
    assert create_response.status_code == 200
    template_id = create_response.json()["id"]

    async with session_maker() as session:
        case = Case(title="Case", created_by="seed")
        session.add(case)
        await session.commit()
        assert case.id is not None
        case_id = case.id

    draft_apply = await client.post(
        f"/api/v1/case-templates/cases/{case_id}/apply/{template_id}",
        cookies={"intercept_session": analyst_cookie},
        json={},
    )
    assert draft_apply.status_code == 400
    assert "published" in draft_apply.json()["detail"]

    publish_response = await client.put(
        f"/api/v1/case-templates/{template_id}",
        cookies={"intercept_session": admin_cookie},
        json={"description": "Now complete", "status": "PUBLISHED"},
    )
    assert publish_response.status_code == 200

    none_selected = await client.post(
        f"/api/v1/case-templates/cases/{case_id}/apply/{template_id}",
        cookies={"intercept_session": analyst_cookie},
        json={"task_overrides": [{"index": 0, "selected": False}]},
    )
    assert none_selected.status_code == 400
    assert "at least one" in none_selected.json()["detail"]
