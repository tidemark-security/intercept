"""Dependency-light password policy shared by schemas and services."""

import re


PASSWORD_POLICY_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{12,}$"
)


class PasswordPolicyViolation(ValueError):
    """Raised when a candidate password does not meet the shared policy."""


def validate_password_policy(password: str) -> str:
    """Return a stripped valid password or raise the canonical policy error."""
    candidate = password.strip()
    if len(candidate) < 12:
        raise PasswordPolicyViolation(
            "Password does not meet minimum length requirements"
        )
    if not PASSWORD_POLICY_REGEX.match(candidate):
        raise PasswordPolicyViolation(
            "Password must include upper, lower, number, and special character"
        )
    return candidate
