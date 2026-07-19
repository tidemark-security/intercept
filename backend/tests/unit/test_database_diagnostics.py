from app.core.database import _redact_database_url


def test_database_diagnostics_hide_password() -> None:
    rendered = _redact_database_url(
        "postgresql+asyncpg://intercept:super-secret@database:5432/intercept"
    )

    assert rendered == "postgresql+asyncpg://intercept:***@database:5432/intercept"
    assert "super-secret" not in rendered
