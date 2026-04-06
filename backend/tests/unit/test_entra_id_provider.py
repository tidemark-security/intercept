import httpx
import pytest

from app.services.enrichment.providers.entra_id import entra_id_provider


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
        assert "oauth2/v2.0/token" in url
        assert data is not None
        assert data["grant_type"] == "client_credentials"
        return FakeResponse(200, {"access_token": "entra-token", "expires_in": 3600})

    async def get(self, url: str, headers: dict[str, str] | None = None, params: dict[str, object] | None = None):
        assert headers is not None
        assert headers.get("Authorization") == "Bearer entra-token"
        if url.endswith("/users/alice@example.com"):
            assert headers == {"Authorization": "Bearer entra-token"}
            return FakeResponse(
                200,
                {
                    "id": "entra-user-1",
                    "displayName": "Alice Analyst",
                    "givenName": "Alice",
                    "surname": "Analyst",
                    "mail": "alice@example.com",
                    "userPrincipalName": "alice@example.com",
                    "jobTitle": "Security Analyst",
                    "department": "SOC",
                    "officeLocation": "HQ",
                    "mobilePhone": "+1-555-0100",
                    "businessPhones": ["+1-555-0110"],
                    "onPremisesSamAccountName": "alice",
                    "employeeId": "E123",
                    "accountEnabled": True,
                },
            )
        if url.endswith("/users/entra-user-1/manager"):
            assert headers == {"Authorization": "Bearer entra-token"}
            return FakeResponse(
                200,
                {
                    "id": "mgr-1",
                    "displayName": "Morgan Manager",
                    "mail": "morgan@example.com",
                    "userPrincipalName": "morgan@example.com",
                },
            )
        if "/users?" in url or url.endswith("/users"):
            assert headers == {"Authorization": "Bearer entra-token"}
            return FakeResponse(
                200,
                {
                    "value": [
                        {
                            "id": "entra-user-2",
                            "displayName": "Bob Builder",
                            "mail": "bob@example.com",
                            "userPrincipalName": "bob@example.com",
                            "department": "IT",
                            "jobTitle": "Engineer",
                            "accountEnabled": True,
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET request: {url} {params}")


class SamLookupAsyncClient(FakeAsyncClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list[tuple[str, dict[str, str] | None, dict[str, object] | None]] = []

    async def get(self, url: str, headers: dict[str, str] | None = None, params: dict[str, object] | None = None):
        self.requests.append((url, headers, params))
        assert headers is not None
        assert headers.get("Authorization") == "Bearer entra-token"

        if url.endswith("/users") and params == {
            "$filter": "mail eq 'corp\\alice'",
            "$select": "id,displayName,givenName,surname,mail,userPrincipalName,jobTitle,department,officeLocation,mobilePhone,businessPhones,onPremisesSamAccountName,employeeId,accountEnabled",
        }:
            assert headers == {"Authorization": "Bearer entra-token"}
            return FakeResponse(200, {"value": []})

        if url.endswith("/users") and params == {
            "$filter": "onPremisesSamAccountName eq 'alice'",
            "$select": "id,displayName,givenName,surname,mail,userPrincipalName,jobTitle,department,officeLocation,mobilePhone,businessPhones,onPremisesSamAccountName,employeeId,accountEnabled",
            "$count": "true",
        }:
            assert headers == {"Authorization": "Bearer entra-token", "ConsistencyLevel": "eventual"}
            return FakeResponse(
                200,
                {
                    "@odata.count": 1,
                    "value": [
                        {
                            "id": "entra-user-sam",
                            "displayName": "Alice Analyst",
                            "givenName": "Alice",
                            "surname": "Analyst",
                            "mail": "alice@example.com",
                            "userPrincipalName": "alice@example.com",
                            "jobTitle": "Security Analyst",
                            "department": "SOC",
                            "officeLocation": "HQ",
                            "mobilePhone": "+1-555-0100",
                            "businessPhones": ["+1-555-0110"],
                            "onPremisesSamAccountName": "alice",
                            "employeeId": "E123",
                            "accountEnabled": True,
                        }
                    ],
                },
            )

        if url.endswith("/users/entra-user-sam/manager"):
            assert headers == {"Authorization": "Bearer entra-token"}
            return FakeResponse(404, {})

        raise AssertionError(f"Unexpected GET request: {url} {params} {headers}")


def test_can_enrich_and_build_cache_key() -> None:
    item = {"type": "internal_actor", "user_id": "Alice@Example.com"}
    assert entra_id_provider.can_enrich(item)
    assert entra_id_provider.build_cache_key(item) == "user:alice@example.com"
    assert not entra_id_provider.can_enrich({"type": "internal_actor"})


@pytest.mark.asyncio
async def test_enrich_fetches_user_and_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.enrichment.providers.entra_id.httpx.AsyncClient", FakeAsyncClient)
    provider = entra_id_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.entra_id.tenant_id": "tenant-id",
            "enrichment.entra_id.client_id": "client-id",
            "enrichment.entra_id.client_secret": "client-secret",
        }
    )

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "entra_id"
    assert result.cache_key == "user:alice@example.com"
    assert result.enrichment_data["display_name"] == "Alice Analyst"
    assert result.enrichment_data["manager_email"] == "morgan@example.com"
    alias_types = {alias.alias_type for alias in result.aliases}
    assert {"email", "upn", "samaccountname", "employee_id"}.issubset(alias_types)


@pytest.mark.asyncio
async def test_enrich_uses_advanced_query_for_sam_account_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SamLookupAsyncClient()
    monkeypatch.setattr("app.services.enrichment.providers.entra_id.httpx.AsyncClient", lambda *args, **kwargs: client)
    provider = entra_id_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.entra_id.tenant_id": "tenant-id",
            "enrichment.entra_id.client_id": "client-id",
            "enrichment.entra_id.client_secret": "client-secret",
        }
    )

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "CORP\\alice"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "entra_id"
    assert result.cache_key == "user:corp\\alice"
    assert result.enrichment_data["sam_account_name"] == "alice"
    assert all(not url.endswith("/users/corp\\alice") for url, _, _ in client.requests)


@pytest.mark.asyncio
async def test_bulk_sync_returns_directory_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.enrichment.providers.entra_id.httpx.AsyncClient", FakeAsyncClient)
    provider = entra_id_provider.__class__()
    settings = StubSettings(
        {
            "enrichment.entra_id.tenant_id": "tenant-id",
            "enrichment.entra_id.client_id": "client-id",
            "enrichment.entra_id.client_secret": "client-secret",
        }
    )

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )

    assert len(results) == 1
    assert results[0].cache_key == "user:bob@example.com"
    assert results[0].enrichment_data["display_name"] == "Bob Builder"