from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCService,
)


ISSUER = "https://idp.example"
CLIENT_ID = "intercept-client"
NONCE = "expected-nonce"
KEY_ID = "test-signing-key"


def _base64url_uint(value: int) -> str:
    width = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def signing_material() -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": KEY_ID,
                "use": "sig",
                "alg": "RS256",
                "n": _base64url_uint(numbers.n),
                "e": _base64url_uint(numbers.e),
            }
        ]
    }
    return private_key, jwks


def _claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "subject-123",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
        "nonce": NONCE,
    }
    claims.update(overrides)
    return claims


def _token(private_key: Any, claims: dict[str, Any]) -> str:
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )


def _validate(
    service: OIDCService,
    signing_material: tuple[Any, dict[str, Any]],
    claims: dict[str, Any],
) -> dict[str, Any]:
    private_key, jwks = signing_material
    return service.validate_id_token(
        id_token=_token(private_key, claims),
        jwks=jwks,
        issuer=ISSUER,
        audience=CLIENT_ID,
        expected_nonce=NONCE,
    )


def test_valid_id_token_claim_contract_is_accepted(
    signing_material: tuple[Any, dict[str, Any]],
) -> None:
    claims = _validate(OIDCService(), signing_material, _claims())

    assert claims["sub"] == "subject-123"


@pytest.mark.parametrize("missing_claim", ["iss", "aud", "sub", "exp", "iat", "nonce"])
def test_each_required_id_token_claim_is_mandatory(
    signing_material: tuple[Any, dict[str, Any]],
    missing_claim: str,
) -> None:
    claims = _claims()
    claims.pop(missing_claim)

    with pytest.raises(OIDCAuthenticationError):
        _validate(OIDCService(), signing_material, claims)


@pytest.mark.parametrize("subject", ["", " ", "x" * 256])
def test_subject_must_be_nonempty_and_bounded(
    signing_material: tuple[Any, dict[str, Any]],
    subject: str,
) -> None:
    with pytest.raises(OIDCAuthenticationError):
        _validate(OIDCService(), signing_material, _claims(sub=subject))


def test_multiple_audiences_require_matching_authorized_party(
    signing_material: tuple[Any, dict[str, Any]],
) -> None:
    with pytest.raises(OIDCAuthenticationError):
        _validate(
            OIDCService(),
            signing_material,
            _claims(aud=[CLIENT_ID, "another-client"]),
        )


@pytest.mark.parametrize(
    "audience",
    [CLIENT_ID, [CLIENT_ID, "another-client"]],
)
def test_present_authorized_party_must_match_client_id(
    signing_material: tuple[Any, dict[str, Any]],
    audience: str | list[str],
) -> None:
    with pytest.raises(OIDCAuthenticationError):
        _validate(
            OIDCService(),
            signing_material,
            _claims(aud=audience, azp="wrong-client"),
        )


def test_matching_authorized_party_is_accepted_for_multiple_audiences(
    signing_material: tuple[Any, dict[str, Any]],
) -> None:
    claims = _validate(
        OIDCService(),
        signing_material,
        _claims(aud=[CLIENT_ID, "another-client"], azp=CLIENT_ID),
    )

    assert claims["azp"] == CLIENT_ID


def test_duplicate_audiences_are_rejected_even_with_matching_authorized_party(
    signing_material: tuple[Any, dict[str, Any]],
) -> None:
    with pytest.raises(OIDCAuthenticationError):
        _validate(
            OIDCService(),
            signing_material,
            _claims(aud=[CLIENT_ID, CLIENT_ID], azp=CLIENT_ID),
        )


def test_iat_beyond_clock_skew_is_rejected(
    signing_material: tuple[Any, dict[str, Any]],
) -> None:
    future = datetime.now(timezone.utc) + timedelta(minutes=5)

    with pytest.raises(OIDCAuthenticationError):
        _validate(
            OIDCService(),
            signing_material,
            _claims(iat=int(future.timestamp())),
        )


@pytest.mark.parametrize("clock_skew", [-1, 301, float("inf"), float("nan")])
def test_clock_skew_must_be_finite_and_safely_bounded(
    signing_material: tuple[Any, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    clock_skew: float,
) -> None:
    monkeypatch.setattr(
        "app.services.oidc_service.get_local",
        lambda key: clock_skew if key == "oidc.clock_skew_seconds" else None,
    )

    with pytest.raises(OIDCConfigurationError, match="clock skew"):
        _validate(OIDCService(), signing_material, _claims())
