from __future__ import annotations

import pytest

from app.services.mcp_oauth_service import MCPOAuthService, OAuthInvalidClientError


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://client.example/oauth/callback",
        "https://client.example:8443/oauth/callback?tenant=one",
        "http://localhost:49152/callback",
        "http://127.0.0.1:49152/callback",
        "http://[::1]:49152/callback",
    ],
)
def test_redirect_validation_accepts_https_and_loopback_callbacks(
    redirect_uri: str,
) -> None:
    assert MCPOAuthService()._validate_redirect_uri(redirect_uri) == redirect_uri


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://client.example/callback",
        "https://user:password@client.example/callback",
        "https://client.example/callback#fragment",
        "javascript:alert(1)",
    ],
)
def test_redirect_validation_rejects_unsafe_callbacks(redirect_uri: str) -> None:
    with pytest.raises(OAuthInvalidClientError):
        MCPOAuthService()._validate_redirect_uri(redirect_uri)
