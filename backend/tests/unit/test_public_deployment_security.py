from __future__ import annotations

import pytest

from app.core.deployment_security import validate_dev_compose_public_exposure


def _hardened_public_environment() -> dict[str, str]:
    return {
        "INTERCEPT_DEV_COMPOSE": "true",
        "INTERCEPT_PUBLIC_ORIGIN": "https://intercept.example.com",
        "POSTGRES_PASSWORD": "rotated-postgres-password",
        "LANGFLOW_DB_PASSWORD": "rotated-langflow-db-password",
        "MINIO_ROOT_USER": "intercept-storage-user",
        "MINIO_ROOT_PASSWORD": "rotated-storage-password",
        "LANGFLOW_SUPERUSER_PASSWORD": "rotated-langflow-admin-password",
        "LANGFLOW_SECRET_KEY": "rotated-langflow-signing-secret",
        "LANGFLOW_API_KEY": "rotated-langflow-api-key",
        "INITIAL_ADMIN_PASSWORD": "Rotated-initial-admin-password1!",
        "SECRET_KEY": "rotated-intercept-application-secret",
    }


def test_local_dev_compose_keeps_convenient_defaults() -> None:
    validate_dev_compose_public_exposure(
        environment={
            "INTERCEPT_DEV_COMPOSE": "true",
            "INTERCEPT_PUBLIC_ORIGIN": "http://127.0.0.1:8080",
        },
        cookie_secure=False,
        trusted_hosts=["localhost", "127.0.0.1"],
    )


def test_non_dev_deployments_are_not_subject_to_dev_compose_defaults() -> None:
    validate_dev_compose_public_exposure(
        environment={"INTERCEPT_PUBLIC_ORIGIN": "https://intercept.example.com"},
        cookie_secure=False,
        trusted_hosts=[],
    )


def test_public_dev_compose_reports_every_unrotated_control() -> None:
    environment = {
        "INTERCEPT_DEV_COMPOSE": "true",
        "INTERCEPT_PUBLIC_ORIGIN": "https://intercept.example.com",
        "POSTGRES_PASSWORD": "intercept_password",
        "LANGFLOW_DB_PASSWORD": "langflow_password",
        "MINIO_ROOT_USER": "minioadmin",
        "MINIO_ROOT_PASSWORD": "minioadmin",
        "LANGFLOW_SUPERUSER_PASSWORD": "admin",
        "LANGFLOW_SECRET_KEY": "3R1HFctPJZ_MDJg-GQe2Z_TaEyZyXQZtbcCR5l8S0E4=",
        "LANGFLOW_API_KEY": "dev-langflow-api-key",
        "INITIAL_ADMIN_PASSWORD": "Dev-initial-admin-password1!",
        "SECRET_KEY": "dev-secret-key-change-in-production",
    }

    with pytest.raises(RuntimeError) as exc_info:
        validate_dev_compose_public_exposure(
            environment=environment,
            cookie_secure=False,
            trusted_hosts=["localhost"],
        )

    message = str(exc_info.value)
    for name in (
        "POSTGRES_PASSWORD",
        "LANGFLOW_DB_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "LANGFLOW_SUPERUSER_PASSWORD",
        "LANGFLOW_SECRET_KEY",
        "LANGFLOW_API_KEY",
        "INITIAL_ADMIN_PASSWORD",
        "SECRET_KEY",
        "SESSION_COOKIE_SECURE",
        "INTERCEPT_TRUSTED_HOSTS",
    ):
        assert name in message
    assert "intercept_password" not in message


def test_public_dev_compose_accepts_rotated_credentials_and_https_controls() -> None:
    validate_dev_compose_public_exposure(
        environment=_hardened_public_environment(),
        cookie_secure=True,
        trusted_hosts=["intercept.example.com"],
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://intercept.example.com",
        "https://user@intercept.example.com",
        "https://intercept.example.com/path",
        "https://intercept.example.com/#fragment",
    ],
)
def test_public_dev_compose_rejects_unsafe_or_noncanonical_origins(origin: str) -> None:
    environment = _hardened_public_environment()
    environment["INTERCEPT_PUBLIC_ORIGIN"] = origin

    with pytest.raises(RuntimeError, match="INTERCEPT_PUBLIC_ORIGIN"):
        validate_dev_compose_public_exposure(
            environment=environment,
            cookie_secure=True,
            trusted_hosts=["intercept.example.com"],
        )
