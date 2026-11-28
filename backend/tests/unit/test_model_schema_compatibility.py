import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.models.models import (
    AlertCreate,
    AlertUpdate,
    CaseReadWithAlerts,
    LinkTemplateUpdate,
    PersonalLinkTemplateUpdate,
    QueueJobsPage,
    TriageRecommendationRead,
)


def test_alert_create_and_update_share_title_length_contract() -> None:
    long_title = "a" * 500

    assert AlertCreate(title=long_title).title == long_title
    assert AlertUpdate(title=long_title).title == long_title

    with pytest.raises(ValidationError):
        AlertCreate(title=long_title + "a")
    with pytest.raises(ValidationError):
        AlertUpdate(title=long_title + "a")


def _openapi_schemas() -> dict[str, dict]:
    test_app = FastAPI()

    @test_app.patch("/link-templates")
    def update_link_template(body: LinkTemplateUpdate) -> LinkTemplateUpdate:
        return body

    @test_app.patch("/personal-link-templates")
    def update_personal_link_template(
        body: PersonalLinkTemplateUpdate,
    ) -> PersonalLinkTemplateUpdate:
        return body

    return test_app.openapi()["components"]["schemas"]


def _validation_contract(model: type[LinkTemplateUpdate], payload: dict) -> list[tuple]:
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    return [
        (error["loc"], error["type"], error["msg"])
        for error in exc_info.value.errors(include_url=False)
    ]


def test_personal_link_template_update_preserves_defaults_and_openapi_contract() -> None:
    expected_defaults = {field_name: None for field_name in LinkTemplateUpdate.model_fields}
    assert LinkTemplateUpdate().model_dump() == expected_defaults
    assert PersonalLinkTemplateUpdate().model_dump() == expected_defaults

    schemas = _openapi_schemas()
    public_schema = schemas["LinkTemplateUpdate"]
    personal_schema = schemas["PersonalLinkTemplateUpdate"]

    assert personal_schema["properties"] == public_schema["properties"]
    assert personal_schema.get("required") == public_schema.get("required")
    assert personal_schema["type"] == public_schema["type"] == "object"
    assert personal_schema["title"] == "PersonalLinkTemplateUpdate"
    assert personal_schema["description"] == "Schema for updating a personal link template."


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"icon_name": "invalid-icon"},
        {"url_template": "javascript:alert(1)"},
        {"surface_scopes": ["entity", "timeline_item"]},
        {"entity_types": ["unknown"]},
    ],
)
def test_personal_link_template_update_preserves_validation(payload: dict) -> None:
    assert _validation_contract(PersonalLinkTemplateUpdate, payload) == _validation_contract(
        LinkTemplateUpdate,
        payload,
    )


def test_personal_link_template_update_preserves_normalization() -> None:
    payload = {
        "name": "  My link  ",
        "tooltip_template": "  Open {{value}}  ",
        "icon_name": "Link2",
        "url_template": "  https://example.test/{{value}}  ",
        "surface_scopes": ["entity"],
        "entity_types": ["alert", "alert", "task"],
    }

    assert PersonalLinkTemplateUpdate.model_validate(payload).model_dump() == (
        LinkTemplateUpdate.model_validate(payload).model_dump()
    )


@pytest.mark.parametrize(
    ("model", "field_names"),
    [
        (
            TriageRecommendationRead,
            [
                "reasoning_bullets",
                "recommended_actions",
                "suggested_tags_add",
                "suggested_tags_remove",
                "applied_changes",
                "applied_context_entries",
            ],
        ),
        (CaseReadWithAlerts, ["alerts"]),
        (QueueJobsPage, ["items"]),
    ],
)
def test_response_collection_defaults_use_factories(model, field_names: list[str]) -> None:
    first = model.model_construct()
    second = model.model_construct()

    for field_name in field_names:
        assert model.model_fields[field_name].default_factory is list
        assert getattr(first, field_name) == []
        assert getattr(first, field_name) is not getattr(second, field_name)
