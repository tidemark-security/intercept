from __future__ import annotations

from typing import Any

import pytest

from app.services.oidc_claim_contract import (
    OIDCClaimContractError,
    validate_oidc_claim_contract,
)


NOW = 2_000_000_000.0
ISSUER = "https://issuer.example"
AUDIENCE = "intercept-client"
NONCE = "server-bound-nonce"


def _claims(**overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "provider-subject",
        "exp": NOW + 300,
        "iat": NOW - 10,
        "nonce": NONCE,
    }
    claims.update(overrides)
    return claims


def _validate(claims: Any, *, require_nonce: bool = True) -> dict[str, Any]:
    return validate_oidc_claim_contract(
        claims,
        issuer=ISSUER,
        audience=AUDIENCE,
        expected_nonce=NONCE,
        require_nonce=require_nonce,
        clock_skew_seconds=30,
        now=NOW,
    )


@pytest.mark.parametrize("claim_name", ["iss", "aud", "sub", "exp", "iat"])
def test_strict_claim_contract_requires_identity_and_time_claims(
    claim_name: str,
) -> None:
    claims = _claims()
    claims.pop(claim_name)

    with pytest.raises(OIDCClaimContractError):
        _validate(claims)


@pytest.mark.parametrize(
    ("claim_name", "value"),
    [
        ("exp", True),
        ("exp", "2000000300"),
        ("exp", float("inf")),
        ("exp", float("nan")),
        ("iat", False),
        ("iat", "1999999990"),
        ("iat", float("inf")),
        ("iat", float("nan")),
    ],
)
def test_strict_claim_contract_rejects_coerced_or_nonfinite_numeric_dates(
    claim_name: str,
    value: Any,
) -> None:
    with pytest.raises(OIDCClaimContractError):
        _validate(_claims(**{claim_name: value}))


@pytest.mark.parametrize(
    "audience",
    [
        "",
        [],
        [AUDIENCE, ""],
        [AUDIENCE, AUDIENCE],
        [AUDIENCE, 7],
        7,
    ],
)
def test_strict_claim_contract_rejects_malformed_audiences(audience: Any) -> None:
    with pytest.raises(OIDCClaimContractError):
        _validate(_claims(aud=audience, azp=AUDIENCE))


@pytest.mark.parametrize("authorized_party", ["", "other-client", 7])
def test_strict_claim_contract_requires_exact_nonempty_authorized_party(
    authorized_party: Any,
) -> None:
    with pytest.raises(OIDCClaimContractError):
        _validate(_claims(aud=[AUDIENCE, "resource-server"], azp=authorized_party))


def test_strict_claim_contract_allows_nonce_omission_only_for_refresh() -> None:
    claims = _claims()
    claims.pop("nonce")

    with pytest.raises(OIDCClaimContractError):
        _validate(claims)
    assert _validate(claims, require_nonce=False)["sub"] == "provider-subject"


def test_strict_claim_contract_checks_optional_refresh_nonce_when_present() -> None:
    with pytest.raises(OIDCClaimContractError):
        _validate(_claims(nonce="different-transaction"), require_nonce=False)


def test_strict_claim_contract_accepts_valid_multi_audience_claims() -> None:
    claims = _validate(
        _claims(aud=[AUDIENCE, "resource-server"], azp=AUDIENCE)
    )

    assert claims["sub"] == "provider-subject"
