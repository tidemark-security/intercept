from __future__ import annotations

import hmac

import pytest

from app.services.mcp_oauth_service import (
    MCPOAuthService,
    OAuthConfigurationError,
    OAuthInvalidClientError,
)


def test_opaque_secret_hash_is_keyed_and_versioned() -> None:
    hashing_key = b"mcp-oauth-hash-key" * 2
    service = MCPOAuthService(token_hash_key=hashing_key)

    expected = hmac.digest(
        hashing_key,
        b"tmoc_high-entropy-authorization-code",
        "sha256",
    ).hex()

    assert service._hash_secret("tmoc_high-entropy-authorization-code") == (
        f"hmac-sha256:v1:{expected}"
    )


def test_opaque_secret_lookup_includes_the_legacy_digest() -> None:
    service = MCPOAuthService(token_hash_key=b"mcp-oauth-hash-key" * 2)

    current_hash, legacy_hash = service._secret_hashes_for_lookup(
        "tmor_existing-refresh-token"
    )

    assert current_hash.startswith("hmac-sha256:v1:")
    assert legacy_hash == service._legacy_hash_secret(
        "tmor_existing-refresh-token"
    )
    assert current_hash != legacy_hash


def test_opaque_secret_hash_rejects_a_short_key() -> None:
    with pytest.raises(OAuthConfigurationError, match="at least 32 bytes"):
        MCPOAuthService(token_hash_key=b"short")


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
