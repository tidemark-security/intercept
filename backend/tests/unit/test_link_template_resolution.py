from app.api.routes.link_templates import _interpolate, _matches_template
from app.models.models import LinkTemplate


def test_interpolate_uses_context_and_user_values_with_url_encoding():
    item = {"device": {"hostname": "host 01"}}
    values = {"tenant": "tenant a"}

    assert (
        _interpolate(
            "https://falcon.example/{{user.tenant}}/{{device.hostname}}",
            item,
            values,
            encode_values=True,
        )
        == "https://falcon.example/tenant%20a/host%2001"
    )
    assert (
        _interpolate(
            "Open {{device.hostname}} in {{user.tenant}}",
            item,
            values,
            encode_values=False,
        )
        == "Open host 01 in tenant a"
    )


def test_interpolate_returns_none_for_missing_placeholders():
    assert _interpolate("https://example/{{user.missing}}", {}, {}, encode_values=True) is None


def test_matches_template_supports_conditions_and_dotted_field_names():
    template = LinkTemplate(
        template_id="crowdstrike-device",
        name="CrowdStrike Device",
        icon_name="CrowdStrikeIcon",
        tooltip_template="{{device.hostname}}",
        url_template="https://example/{{device.hostname}}",
        field_names=["device.hostname"],
        conditions={"type": "host"},
    )

    assert _matches_template(template, {"type": "host", "device": {"hostname": "host01"}})
    assert not _matches_template(template, {"type": "user", "device": {"hostname": "host01"}})
    assert not _matches_template(template, {"type": "host", "device": {}})
