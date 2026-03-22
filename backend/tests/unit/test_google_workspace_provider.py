import json

import httpx
import pytest

from app.services.enrichment.providers.google_workspace import _normalize_private_key, google_workspace_provider


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, data: dict[str, object] | None = None):
        assert "oauth2.googleapis.com/token" in url
        assert data is not None
        assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
        return FakeResponse(200, {"access_token": "google-token", "expires_in": 3600})

    async def get(self, url: str, headers: dict[str, str] | None = None, params: dict[str, object] | None = None):
        assert headers == {"Authorization": "Bearer google-token"}
        if url.endswith("/users/alice@example.com"):
            return FakeResponse(
                200,
                {
                    "id": "google-user-1",
                    "primaryEmail": "alice@example.com",
                    "name": {
                        "fullName": "Alice Analyst",
                        "givenName": "Alice",
                        "familyName": "Analyst",
                    },
                    "organizations": [{"title": "Security Analyst", "department": "SOC", "name": "Tidemark"}],
                    "phones": [{"value": "+1-555-0100"}],
                    "aliases": ["alice.alias@example.com"],
                    "emails": [{"address": "alice.alt@example.com"}],
                    "orgUnitPath": "/Security",
                    "suspended": False,
                },
            )
        if url.endswith("/users"):
            return FakeResponse(
                200,
                {
                    "users": [
                        {
                            "id": "google-user-2",
                            "primaryEmail": "bob@example.com",
                            "name": {
                                "fullName": "Bob Builder",
                                "givenName": "Bob",
                                "familyName": "Builder",
                            },
                            "organizations": [{"title": "Engineer", "department": "IT", "name": "Tidemark"}],
                            "phones": [],
                            "aliases": [],
                            "emails": [],
                            "orgUnitPath": "/IT",
                            "suspended": False,
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET request: {url} {params}")


def test_can_enrich_and_build_cache_key() -> None:
    item = {"type": "internal_actor", "user_id": "Alice@Example.com"}
    assert google_workspace_provider.can_enrich(item)
    assert google_workspace_provider.build_cache_key(item) == "user:alice@example.com"
    assert not google_workspace_provider.can_enrich({"type": "internal_actor"})


def test_normalize_private_key_handles_escaped_newlines() -> None:
    raw = "-----BEGIN PRIVATE KEY-----\\nabc123\\n-----END PRIVATE KEY-----\\n"

    normalized = _normalize_private_key(raw)

    assert normalized == "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----\n"


def test_normalize_private_key_handles_json_wrapped_string() -> None:
    raw = json.dumps("-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----\n")

    normalized = _normalize_private_key(raw)

    assert normalized == "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"


@pytest.mark.asyncio
async def test_enrich_fetches_google_workspace_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.enrichment.providers.google_workspace.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace._build_jwt",
        lambda service_account, subject_email: "signed-jwt",
    )
    provider = google_workspace_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.google_workspace.client_email": "svc@example.com",
            "enrichment.google_workspace.private_key": "key",
            "enrichment.google_workspace.token_uri": "https://oauth2.googleapis.com/token",
            "enrichment.google_workspace.admin_email": "admin@example.com",
            "enrichment.google_workspace.domain": "example.com",
        }
    )

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "google_workspace"
    assert result.cache_key == "user:alice@example.com"
    assert result.enrichment_data["org_unit_path"] == "/Security"
    alias_values = {alias.alias_value for alias in result.aliases}
    assert "alice.alias@example.com" in alias_values
    assert "alice.alt@example.com" in alias_values


@pytest.mark.asyncio
async def test_bulk_sync_returns_google_workspace_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.enrichment.providers.google_workspace.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace._build_jwt",
        lambda service_account, subject_email: "signed-jwt",
    )
    provider = google_workspace_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.google_workspace.client_email": "svc@example.com",
            "enrichment.google_workspace.private_key": "key",
            "enrichment.google_workspace.token_uri": "https://oauth2.googleapis.com/token",
            "enrichment.google_workspace.admin_email": "admin@example.com",
            "enrichment.google_workspace.domain": "example.com",
        }
    )

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )

    assert len(results) == 1
    assert results[0].cache_key == "user:bob@example.com"
    assert results[0].enrichment_data["display_name"] == "Bob Builder"


@pytest.mark.asyncio
async def test_get_settings_falls_back_to_legacy_service_account_json() -> None:
    provider = google_workspace_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.google_workspace.service_account_json": '{"client_email":"svc@example.com","private_key":"-----BEGIN PRIVATE KEY-----\\nkey\\n-----END PRIVATE KEY-----\\n","token_uri":"https://oauth2.googleapis.com/token"}',
            "enrichment.google_workspace.admin_email": "admin@example.com",
        }
    )

    cfg = await provider._get_settings(settings)  # type: ignore[arg-type]

    assert cfg is not None
    assert cfg["service_account"]["client_email"] == "svc@example.com"
    assert cfg["service_account"]["private_key"] == "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----"