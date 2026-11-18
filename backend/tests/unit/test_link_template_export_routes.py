from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.link_templates import (
    export_link_templates,
    export_personal_link_templates,
)
from app.models.models import (
    LinkTemplate,
    LinkTemplateExportRequest,
    PersonalLinkTemplate,
)


def _template_fields() -> dict[str, Any]:
    return {
        "template_id": "case-console",
        "name": "Case Console",
        "icon_name": "Link2",
        "tooltip_template": "Open {{human_id}}",
        "url_template": "https://console.example/cases/{{human_id}}",
        "field_names": ["human_id"],
        "conditions": None,
        "surface_scopes": ["entity"],
        "entity_types": ["case"],
        "enabled": True,
        "display_order": 10,
    }


def _db_returning(rows: list[LinkTemplate | PersonalLinkTemplate]) -> AsyncSession:
    scalar_result = SimpleNamespace(all=lambda: rows)
    result = SimpleNamespace(scalars=lambda: scalar_result)
    return cast(AsyncSession, SimpleNamespace(execute=AsyncMock(return_value=result)))


@pytest.mark.asyncio
async def test_public_and_personal_exports_share_the_portable_bundle_contract() -> None:
    owner_id = uuid4()
    public_db = _db_returning([LinkTemplate(id=11, **_template_fields())])
    personal_db = _db_returning(
        [PersonalLinkTemplate(id=22, user_id=owner_id, **_template_fields())]
    )

    public_bundle = await export_link_templates(
        request=LinkTemplateExportRequest(template_ids=[11]),
        db=public_db,
        _=SimpleNamespace(),
    )
    personal_bundle = await export_personal_link_templates(
        request=LinkTemplateExportRequest(template_ids=[22]),
        db=personal_db,
        current_user=SimpleNamespace(id=owner_id),
    )

    expected_bundle = {
        "schema_version": 1,
        "templates": [_template_fields()],
    }
    assert public_bundle.model_dump() == expected_bundle
    assert personal_bundle.model_dump() == expected_bundle

    personal_statement = personal_db.execute.await_args.args[0]  # type: ignore[attr-defined]
    personal_sql = str(personal_statement)
    assert "personal_link_templates.user_id =" in personal_sql
    assert owner_id in personal_statement.compile().params.values()
    assert (
        "ORDER BY personal_link_templates.display_order, personal_link_templates.name"
        in personal_sql
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("personal", [False, True], ids=["public", "personal"])
async def test_exports_reject_an_empty_selection_without_querying(personal: bool) -> None:
    db = _db_returning([])
    request = LinkTemplateExportRequest()

    with pytest.raises(HTTPException) as exc_info:
        if personal:
            await export_personal_link_templates(
                request=request,
                db=db,
                current_user=SimpleNamespace(id=uuid4()),
            )
        else:
            await export_link_templates(
                request=request,
                db=db,
                _=SimpleNamespace(),
            )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert exc_info.value.detail == "template_ids must contain at least one template id"
    db.execute.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("personal", "expected_detail"),
    [
        (False, "Link templates not found: [99, 42]"),
        (True, "Personal link templates not found: [99, 42]"),
    ],
    ids=["public", "personal"],
)
async def test_exports_report_missing_ids_in_request_order(
    personal: bool,
    expected_detail: str,
) -> None:
    db = _db_returning([])
    request = LinkTemplateExportRequest(template_ids=[99, 42])

    with pytest.raises(HTTPException) as exc_info:
        if personal:
            await export_personal_link_templates(
                request=request,
                db=db,
                current_user=SimpleNamespace(id=uuid4()),
            )
        else:
            await export_link_templates(
                request=request,
                db=db,
                _=SimpleNamespace(),
            )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == expected_detail
