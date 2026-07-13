from app.api.routes.link_templates import (
    _interpolate,
    _is_safe_resolved_url,
    _matches_template,
    _normalize_extra_url_schemes,
    _with_copy_suffix,
)
import pytest
from pydantic import ValidationError

from app.models.models import LinkTemplate, PortableLinkTemplate


def test_interpolate_uses_context_and_user_values_with_url_encoding():
    item = {"device": {"hostname": "host 01"}, "tenant": "tenant a"}

    assert (
        _interpolate(
            "https://falcon.example/{{tenant}}/{{device.hostname}}",
            item,
            encode_values=True,
        )
        == "https://falcon.example/tenant%20a/host%2001"
    )
    assert (
        _interpolate(
            "Open {{device.hostname}} in {{tenant}}",
            item,
            encode_values=False,
        )
        == "Open host 01 in tenant a"
    )


def test_interpolate_returns_none_for_missing_placeholders():
    assert _interpolate("https://example/{{missing}}", {}, encode_values=True) is None


def test_matches_template_supports_scope_conditions_and_dotted_field_names():
    template = LinkTemplate(
        template_id="crowdstrike-device",
        name="CrowdStrike Device",
        icon_name="CrowdStrikeIcon",
        tooltip_template="{{device.hostname}}",
        url_template="https://example/{{device.hostname}}",
        field_names=["device.hostname"],
        conditions={"type": "host"},
        surface_scopes=["entity"],
        entity_types=["case"],
    )

    assert _matches_template(
        template,
        {"type": "host", "device": {"hostname": "host01"}},
        surface="entity",
        entity_type="case",
    )
    assert not _matches_template(
        template,
        {"type": "host", "device": {"hostname": "host01"}},
        surface="timeline_item",
        entity_type="case",
    )
    assert not _matches_template(
        template,
        {"type": "host", "device": {"hostname": "host01"}},
        surface="entity",
        entity_type="alert",
    )
    assert not _matches_template(
        template,
        {"type": "user", "device": {"hostname": "host01"}},
        surface="entity",
        entity_type="case",
    )
    assert not _matches_template(
        template,
        {"type": "host", "device": {}},
        surface="entity",
        entity_type="case",
    )


def test_safe_resolved_url_allows_expected_schemes_only():
    assert _is_safe_resolved_url("https://example.com")
    assert _is_safe_resolved_url("mailto:analyst@example.com")
    assert _is_safe_resolved_url("tel:+15551212")
    assert _is_safe_resolved_url("claude://open/case", {"http", "https", "mailto", "tel", "claude"})
    assert not _is_safe_resolved_url("javascript:alert(1)")
    assert not _is_safe_resolved_url("")


def test_extra_url_scheme_normalization_drops_invalid_and_dangerous_values():
    assert _normalize_extra_url_schemes(["Claude:", "foo+bar", "javascript", "", 123]) == {
        "claude",
        "foo+bar",
    }


def test_portable_link_template_rejects_unsafe_url_templates_on_import():
    with pytest.raises(ValidationError, match="url_template"):
        PortableLinkTemplate(
            template_id="unsafe",
            name="Unsafe",
            icon_name="Link2",
            tooltip_template="Open {{human_id}}",
            url_template="javascript:alert({{human_id}})",
            surface_scopes=["entity"],
        )


@pytest.mark.parametrize("surface_scopes", [[], ["entity", "timeline_item"], ["entity", "entity"]])
def test_portable_link_template_rejects_invalid_surface_scope_shapes(surface_scopes):
    with pytest.raises(ValidationError, match="surface_scopes"):
        PortableLinkTemplate(
            template_id="invalid-surface",
            name="Invalid Surface",
            icon_name="Link2",
            tooltip_template="Open {{human_id}}",
            url_template="https://example/{{human_id}}",
            surface_scopes=surface_scopes,
        )


def test_with_copy_suffix_uses_incrementing_template_id():
    existing = {"vt-domain", "vt-domain-copy", "vt-domain-copy-2"}

    assert _with_copy_suffix("new-template", existing) == "new-template"
    assert _with_copy_suffix("vt-domain", existing) == "vt-domain-copy-3"
