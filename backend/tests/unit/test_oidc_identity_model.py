from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.models import UserAccount


@pytest.mark.parametrize(
    ("oidc_issuer", "oidc_subject"),
    [
        ("https://issuer.example", None),
        (None, "provider-subject"),
        ("", "provider-subject"),
        ("https://issuer.example", ""),
        ("   ", "provider-subject"),
        ("https://issuer.example", "   "),
        (" \t\n\r\f\v", "provider-subject"),
        ("https://issuer.example", " \t\n\r\f\v"),
    ],
)
def test_user_account_requires_complete_nonblank_oidc_identity_pair(
    oidc_issuer: str | None,
    oidc_subject: str | None,
) -> None:
    with pytest.raises(ValidationError, match="OIDC issuer and subject"):
        UserAccount.model_validate(
            {
                "username": "invalid.oidc.identity",
                "oidc_issuer": oidc_issuer,
                "oidc_subject": oidc_subject,
            }
        )
