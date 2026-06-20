import httpx
import pytest

from app.services.enrichment.providers.servicenow import servicenow_provider


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
    requests: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.auth = kwargs.get("auth")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        assert self.auth == ("svc_user", "svc_pass")
        assert url == "https://example.service-now.com/api/now/table/sys_user"
        params = params or {}
        self.requests.append(dict(params))
        if params.get("sysparm_limit") == 1 and "sysparm_offset" not in params:
            return FakeResponse(
                200,
                {
                    "result": [
                        {
                            "sys_id": "sn-user-1",
                            "user_name": "alice",
                            "email": "alice@example.com",
                            "name": "Alice Analyst",
                            "first_name": "Alice",
                            "last_name": "Analyst",
                            "title": "Security Analyst",
                            "department": {"display_value": "SOC", "value": "dept-1"},
                            "company": {"display_value": "Tidemark", "value": "company-1"},
                            "active": "true",
                        }
                    ]
                },
            )

        offset = int(params.get("sysparm_offset", 0))
        if offset == 0:
            return FakeResponse(
                200,
                {
                    "result": [
                        {"sys_id": "sn-user-2", "user_name": "bob", "email": "bob@example.com", "name": "Bob Builder"},
                        {
                            "sys_id": "sn-user-3",
                            "user_name": "carol",
                            "email": "carol@example.com",
                            "name": "Carol Coder",
                        },
                    ]
                },
            )
        return FakeResponse(200, {"result": [{"sys_id": "sn-user-4", "user_name": "dan", "email": "dan@example.com"}]})


def _settings(**overrides: object) -> StubSettings:
    values: dict[str, object] = {
        "enrichment.servicenow.instance_url": "https://example.service-now.com/",
        "enrichment.servicenow.username": "svc_user",
        "enrichment.servicenow.password": "svc_pass",
        "enrichment.servicenow.table": "sys_user",
        "enrichment.servicenow.fields": "sys_id,user_name,email,name,title,department,company,active",
        "enrichment.servicenow.lookup_query_template": "email={value}^ORuser_name={value}",
        "enrichment.servicenow.bulk_sync_query": "active=true",
        "enrichment.servicenow.page_size": 2,
        "enrichment.servicenow.max_records": 3,
    }
    values.update(overrides)
    return StubSettings(values)


def test_can_enrich_and_build_cache_key() -> None:
    item = {"type": "internal_actor", "user_id": "Alice@Example.com"}
    assert servicenow_provider.can_enrich(item)
    assert servicenow_provider.build_cache_key(item) == "user:alice@example.com"
    assert not servicenow_provider.can_enrich({"type": "internal_actor"})


@pytest.mark.asyncio
async def test_enrich_fetches_servicenow_user(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FakeAsyncClient)
    provider = servicenow_provider.__class__()

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "servicenow"
    assert result.cache_key == "user:alice@example.com"
    assert result.enrichment_data["department"] == "SOC"
    alias_values = {alias.alias_value for alias in result.aliases}
    assert {"sn-user-1", "alice", "alice@example.com", "alice analyst"} <= alias_values
    assert FakeAsyncClient.requests[0]["sysparm_query"] == "email=alice@example.com^ORuser_name=alice@example.com"


@pytest.mark.asyncio
async def test_bulk_sync_is_bounded_by_configured_max_records(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FakeAsyncClient)
    provider = servicenow_provider.__class__()

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
    )

    assert [result.cache_key for result in results] == [
        "user:bob@example.com",
        "user:carol@example.com",
        "user:dan@example.com",
    ]
    assert [request["sysparm_limit"] for request in FakeAsyncClient.requests] == [2, 1]
    assert [request["sysparm_offset"] for request in FakeAsyncClient.requests] == [0, 2]
    assert all(request["sysparm_query"] == "active=true" for request in FakeAsyncClient.requests)


@pytest.mark.asyncio
async def test_get_settings_clamps_bulk_sync_bounds() -> None:
    provider = servicenow_provider.__class__()

    cfg = await provider._get_settings(  # type: ignore[arg-type]
        _settings(
            **{
                "enrichment.servicenow.page_size": 50000,
                "enrichment.servicenow.max_records": 999999,
            }
        )
    )

    assert cfg is not None
    assert cfg["page_size"] == 1000
    assert cfg["max_records"] == 50000
