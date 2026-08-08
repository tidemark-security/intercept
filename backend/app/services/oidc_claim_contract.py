"""Strict, provider-independent validation for OIDC identity claims."""

from __future__ import annotations

import hmac
import math
import time
from typing import Any


class OIDCClaimContractError(ValueError):
    """An otherwise verified ID token violates Intercept's claim contract."""


def validate_oidc_clock_skew(value: Any) -> float:
    """Return a finite clock skew within Intercept's supported safety bound."""

    if isinstance(value, bool):
        raise ValueError("OIDC clock skew must be numeric")
    try:
        clock_skew_seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OIDC clock skew must be numeric") from exc
    if not math.isfinite(clock_skew_seconds) or not 0 <= clock_skew_seconds <= 300:
        raise ValueError("OIDC clock skew must be between 0 and 300 seconds")
    return clock_skew_seconds


def _numeric_date(claims: dict[str, Any], name: str) -> float:
    value = claims.get(name)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise OIDCClaimContractError(f"OIDC {name} claim is invalid")
    return float(value)


def validate_oidc_claim_contract(
    claims: Any,
    *,
    issuer: str,
    audience: str,
    expected_nonce: str | None,
    require_nonce: bool,
    clock_skew_seconds: float,
    now: float | None = None,
) -> dict[str, Any]:
    """Apply one strict OIDC claim contract after cryptographic verification.

    Cryptographic signature, locked algorithm, and JWKS validation remain the
    caller's responsibility. This function deliberately does not coerce claim
    values: JSON booleans and strings are not NumericDate values, and malformed
    audience containers cannot become valid through string conversion.
    """

    if not isinstance(claims, dict):
        raise OIDCClaimContractError("OIDC claims must be a JSON object")
    if not isinstance(issuer, str) or not issuer:
        raise OIDCClaimContractError("OIDC expected issuer is invalid")
    if not isinstance(audience, str) or not audience:
        raise OIDCClaimContractError("OIDC expected audience is invalid")
    try:
        skew = validate_oidc_clock_skew(clock_skew_seconds)
    except ValueError as exc:
        raise OIDCClaimContractError(str(exc)) from exc

    validation_time = time.time() if now is None else now
    if (
        not isinstance(validation_time, (int, float))
        or isinstance(validation_time, bool)
        or not math.isfinite(float(validation_time))
    ):
        raise OIDCClaimContractError("OIDC validation time is invalid")
    validation_time = float(validation_time)

    token_issuer = claims.get("iss")
    if not isinstance(token_issuer, str) or not hmac.compare_digest(
        token_issuer,
        issuer,
    ):
        raise OIDCClaimContractError("OIDC issuer claim is invalid")

    subject = claims.get("sub")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject) > 255
    ):
        raise OIDCClaimContractError("OIDC subject claim is invalid")

    expires_at = _numeric_date(claims, "exp")
    issued_at = _numeric_date(claims, "iat")
    if expires_at <= validation_time - skew:
        raise OIDCClaimContractError("OIDC ID token has expired")
    if issued_at > validation_time + skew:
        raise OIDCClaimContractError("OIDC iat claim is in the future")
    if issued_at > expires_at:
        raise OIDCClaimContractError("OIDC token issue time is after expiry")

    token_audience = claims.get("aud")
    if isinstance(token_audience, str):
        if not token_audience:
            raise OIDCClaimContractError("OIDC audience claim is invalid")
        audiences = [token_audience]
    elif isinstance(token_audience, list):
        if (
            not token_audience
            or not all(isinstance(item, str) and item for item in token_audience)
            or len(set(token_audience)) != len(token_audience)
        ):
            raise OIDCClaimContractError("OIDC audience claim is invalid")
        audiences = token_audience
    else:
        raise OIDCClaimContractError("OIDC audience claim is invalid")
    if not any(hmac.compare_digest(item, audience) for item in audiences):
        raise OIDCClaimContractError("OIDC audience validation failed")

    authorized_party = claims.get("azp")
    if len(audiences) > 1 and authorized_party is None:
        raise OIDCClaimContractError(
            "OIDC authorized party is required for multiple audiences"
        )
    if authorized_party is not None:
        if (
            not isinstance(authorized_party, str)
            or not authorized_party
            or not hmac.compare_digest(authorized_party, audience)
        ):
            raise OIDCClaimContractError(
                "OIDC authorized party validation failed"
            )

    nonce = claims.get("nonce")
    if nonce is None:
        if require_nonce:
            raise OIDCClaimContractError("OIDC nonce claim is required")
    elif (
        not isinstance(nonce, str)
        or not nonce
        or not isinstance(expected_nonce, str)
        or not hmac.compare_digest(nonce, expected_nonce)
    ):
        raise OIDCClaimContractError("OIDC nonce validation failed")

    return dict(claims)


__all__ = [
    "OIDCClaimContractError",
    "validate_oidc_claim_contract",
    "validate_oidc_clock_skew",
]
