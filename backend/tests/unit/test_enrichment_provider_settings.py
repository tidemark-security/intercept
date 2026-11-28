from unittest.mock import AsyncMock

import pytest

from app.core.settings_registry import get_setting_default
from app.services.enrichment.base import EnrichmentProvider, EnrichmentProviderError
from app.services.enrichment.providers.ldap_provider import ldap_provider


@pytest.mark.asyncio
async def test_provider_setting_values_use_canonical_registry_defaults() -> None:
    settings = AsyncMock()
    settings.get_many.side_effect = lambda defaults: defaults
    provider = ldap_provider.__class__()

    values = await provider._get_setting_values(  # type: ignore[attr-defined]
        settings,
        ("use_ssl", "user_search_filter"),
    )

    assert values == {
        "use_ssl": get_setting_default("enrichment.ldap.use_ssl"),
        "user_search_filter": get_setting_default(
            "enrichment.ldap.user_search_filter"
        ),
    }
    settings.get_many.assert_awaited_once_with(
        {
            "enrichment.ldap.use_ssl": get_setting_default(
                "enrichment.ldap.use_ssl"
            ),
            "enrichment.ldap.user_search_filter": get_setting_default(
                "enrichment.ldap.user_search_filter"
            ),
        }
    )


@pytest.mark.asyncio
async def test_provider_setting_values_reject_unknown_relative_names() -> None:
    settings = AsyncMock()
    provider = ldap_provider.__class__()

    with pytest.raises(KeyError, match="enrichment\\.ldap\\.unknown"):
        await provider._get_setting_values(  # type: ignore[attr-defined]
            settings,
            ("unknown",),
        )

    settings.get_many.assert_not_awaited()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "must be an object"),
        ({}, "missing access_token"),
        ({"access_token": "token", "expires_in": "invalid"}, "invalid expires_in"),
    ],
)
def test_oauth_token_response_validation_rejects_malformed_payloads(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(EnrichmentProviderError, match=message):
        EnrichmentProvider._parse_oauth_access_token_response(
            payload,
            provider_name="Example",
        )


def test_oauth_token_response_validation_normalizes_token_and_expiry() -> None:
    token, expires_in = EnrichmentProvider._parse_oauth_access_token_response(
        {"access_token": "  token  ", "expires_in": "7200"},
        provider_name="Example",
    )

    assert token == "token"
    assert expires_in == 7200
