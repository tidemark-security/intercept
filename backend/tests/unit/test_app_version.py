from app.main import APP_VERSION, api_app


def test_application_metadata_uses_configured_version() -> None:
    assert api_app.version == APP_VERSION
    assert api_app.openapi()["info"]["version"] == APP_VERSION


def test_openapi_advertises_bearer_auth_for_protected_router_operations() -> None:
    schema = api_app.openapi()
    assert schema["paths"]["/api/v1/admin/audit"]["get"]["security"] == [{"BearerAuth": []}]
    assert "security" not in schema["paths"]["/health"]["get"]
