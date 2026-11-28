import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import import_key

from app.services.enrichment.providers.google_workspace import (
    _build_jwt,
    _normalize_private_key,
    google_workspace_provider,
)


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)

    async def get_many(self, defaults: dict[str, object]) -> dict[str, object]:
        return {key: self._values.get(key, default) for key, default in defaults.items()}


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


def test_build_jwt_signs_rs256_service_account_assertion() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    token = _build_jwt(
        {
            "client_email": "service-account@example.com",
            "private_key": private_pem,
            "private_key_id": "key-id-1",
        },
        "admin@example.com",
    )
    decoded = jwt.decode(
        token,
        import_key(public_pem, "RSA"),
        algorithms=["RS256"],
    )

    assert decoded.header["alg"] == "RS256"
    assert decoded.header["kid"] == "key-id-1"
    assert decoded.claims["iss"] == "service-account@example.com"
    assert decoded.claims["sub"] == "admin@example.com"


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


@pytest.mark.asyncio
async def test_bulk_sync_skips_only_malformed_provider_records(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class MixedRecordAsyncClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, object] | None = None,
        ):
            assert headers == {"Authorization": "Bearer google-token"}
            return FakeResponse(
                200,
                {
                    "users": [
                        {
                            "id": "sensitive-malformed-google-id",
                            "primaryEmail": ["not-a-string"],
                        },
                        {
                            "id": "google-user-valid",
                            "primaryEmail": "valid@example.com",
                            "name": {"fullName": "Valid User"},
                            "suspended": False,
                        },
                    ]
                },
            )

    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace.httpx.AsyncClient",
        MixedRecordAsyncClient,
    )
    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace._build_jwt",
        lambda service_account, subject_email: "signed-jwt",
    )
    provider = google_workspace_provider.__class__()

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=StubSettings(
            {
                "enrichment.google_workspace.client_email": "svc@example.com",
                "enrichment.google_workspace.private_key": "key",
                "enrichment.google_workspace.admin_email": "admin@example.com",
                "enrichment.google_workspace.domain": "example.com",
            }
        ),  # type: ignore[arg-type]
    )

    assert [result.cache_key for result in results] == ["user:valid@example.com"]
    assert (
        "Google Workspace bulk sync skipped malformed user records (count=1)"
        in caplog.messages
    )
    assert "sensitive-malformed-google-id" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError, AttributeError])
async def test_bulk_sync_propagates_unexpected_record_processing_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "app.services.enrichment.providers.google_workspace._build_jwt",
        lambda service_account, subject_email: "signed-jwt",
    )
    provider = google_workspace_provider.__class__()

    def raise_defect(*args, **kwargs):
        raise error_type("record processing defect")

    monkeypatch.setattr(provider, "_build_result", raise_defect)

    with pytest.raises(error_type, match="record processing defect"):
        await provider.bulk_sync(
            db=None,  # type: ignore[arg-type]
            settings=StubSettings(
                {
                    "enrichment.google_workspace.client_email": "svc@example.com",
                    "enrichment.google_workspace.private_key": "key",
                    "enrichment.google_workspace.admin_email": "admin@example.com",
                    "enrichment.google_workspace.domain": "example.com",
                }
            ),  # type: ignore[arg-type]
        )
