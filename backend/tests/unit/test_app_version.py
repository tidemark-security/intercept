from app.main import APP_VERSION, api_app


def test_application_metadata_uses_configured_version() -> None:
    assert api_app.version == APP_VERSION
    assert api_app.openapi()["info"]["version"] == APP_VERSION
