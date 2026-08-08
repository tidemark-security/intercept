import httpx
import pytest
import sys
import types

from app.services.enrichment.providers.servicenow import servicenow_provider


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
    requests: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.auth = kwargs.get("auth")
        self.headers = kwargs.get("headers") or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        if self.auth is not None:
            assert self.auth == ("svc_user", "svc_pass")
        if self.headers:
            assert self.headers == {"Authorization": "Bearer oauth-access-token"}
        assert url == "https://example.service-now.com/api/now/table/sys_user"
        params = params or {}
        self.requests.append(dict(params))
        if params.get("sysparm_limit") == 2 and "sysparm_offset" not in params:
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
                            "vip": "true",
                            "u_privileged_user": "1",
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
        "enrichment.servicenow.user_query_field": "email,user_name",
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
    assert result.enrichment_data["source_table"] == "sys_user"
    assert result.enrichment_data["record_id"] == "sn-user-1"
    assert result.enrichment_data["record_link"] == "https://example.service-now.com/sys_user.do?sys_id=sn-user-1"
    assert result.enrichment_data["matched_identifier"] == "alice@example.com"
    assert result.enrichment_data["department"] == "SOC"
    assert result.enrichment_data["is_vip"] is True
    assert result.enrichment_data["is_privileged"] is True
    assert result.enrichment_data["mapped_fields"] == {
        "vip": {"field": "vip", "value": "true", "values": {"vip": "true"}, "mapped": True},
        "privileged": {
            "field": "u_privileged_user",
            "value": "1",
            "values": {"u_privileged_user": "1"},
            "mapped": True,
        },
    }
    alias_values = {alias.alias_value for alias in result.aliases}
    assert {"sn-user-1", "alice", "alice@example.com", "alice analyst"} <= alias_values
    assert (
        FakeAsyncClient.requests[0]["sysparm_query"]
        == "email=alice@example.com^ORuser_name=alice@example.com^active=true"
    )
    assert FakeAsyncClient.requests[0]["sysparm_limit"] == 2


@pytest.mark.asyncio
async def test_enrich_supports_pysnow_oauth_password_client(monkeypatch: pytest.MonkeyPatch) -> None:
    offloaded: list[object] = []

    async def run_inline(callback):
        offloaded.append(callback)
        return callback()

    class FakeOAuthClient:
        generated: list[tuple[str, str]] = []
        token: dict[str, object] | None = None

        def __init__(self, **kwargs):
            assert kwargs == {
                "host": "example.service-now.com",
                "use_ssl": True,
                "client_id": "oauth-client",
                "client_secret": "oauth-secret",
            }

        def generate_token(self, user: str, password: str) -> dict[str, object]:
            self.generated.append((user, password))
            return {
                "token_type": "Bearer",
                "refresh_token": "refresh-token",
                "access_token": "oauth-access-token",
                "scope": "useraccount",
                "expires_in": 3600,
                "expires_at": 1234567890,
            }

        def set_token(self, token: dict[str, object]) -> None:
            self.token = token

    FakeAsyncClient.requests = []
    fake_pysnow = types.SimpleNamespace(OAuthClient=FakeOAuthClient)
    monkeypatch.setitem(sys.modules, "pysnow", fake_pysnow)
    monkeypatch.setattr(
        "app.services.enrichment.providers.servicenow.asyncio.to_thread",
        run_inline,
    )
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FakeAsyncClient)
    provider = servicenow_provider.__class__()

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(
            **{
                "enrichment.servicenow.auth_type": "oauth_password",
                "enrichment.servicenow.oauth_client_id": "oauth-client",
                "enrichment.servicenow.oauth_client_secret": "oauth-secret",
            }
        ),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.cache_key == "user:alice@example.com"
    assert FakeOAuthClient.generated == [("svc_user", "svc_pass")]
    assert len(offloaded) == 1


@pytest.mark.asyncio
async def test_enrich_returns_error_for_ambiguous_servicenow_user(monkeypatch: pytest.MonkeyPatch) -> None:
    class AmbiguousAsyncClient(FakeAsyncClient):
        async def get(self, url: str, params: dict[str, object] | None = None):
            return FakeResponse(
                200,
                {
                    "result": [
                        {"sys_id": "sn-user-1", "email": "alice@example.com"},
                        {"sys_id": "sn-user-2", "email": "alice@example.com"},
                    ]
                },
            )

    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", AmbiguousAsyncClient)
    provider = servicenow_provider.__class__()

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data == {
        "error": "Ambiguous user lookup: alice@example.com",
        "matched_identifier": "alice@example.com",
    }


def test_build_result_preserves_false_vip_and_privileged_values() -> None:
    provider = servicenow_provider.__class__()

    result = provider._build_result(  # type: ignore[attr-defined]
        {
            "sys_id": "sn-user-4",
            "user_name": "dan",
            "email": "dan@example.com",
            "name": "Dan Defender",
            "vip": "false",
            "u_privileged_user": "0",
        },
        cache_key="user:dan@example.com",
        cfg={
            "instance_url": "https://example.service-now.com",
            "table": "sys_user",
            "user_vip_field": "vip",
            "user_privileged_field": "u_privileged_user",
        },
        matched_identifier="dan@example.com",
    )

    assert result.enrichment_data["is_vip"] is False
    assert result.enrichment_data["is_privileged"] is False
    assert result.enrichment_data["mapped_fields"]["vip"]["mapped"] is False
    assert result.enrichment_data["mapped_fields"]["privileged"]["mapped"] is False


def test_build_result_supports_multiple_vip_and_privileged_fields() -> None:
    provider = servicenow_provider.__class__()

    result = provider._build_result(  # type: ignore[attr-defined]
        {
            "sys_id": "sn-user-5",
            "user_name": "erin",
            "email": "erin@example.com",
            "name": "Erin Escalation",
            "vip": "false",
            "u_vip_alt": "true",
            "u_privileged_user": "0",
            "u_admin": "yes",
        },
        cache_key="user:erin@example.com",
        cfg={
            "instance_url": "https://example.service-now.com",
            "table": "sys_user",
            "user_vip_field": "vip,u_vip_alt",
            "user_privileged_field": "u_privileged_user,u_admin",
        },
        matched_identifier="erin@example.com",
    )

    assert result.enrichment_data["is_vip"] is True
    assert result.enrichment_data["is_privileged"] is True
    assert result.enrichment_data["mapped_fields"]["vip"]["values"] == {
        "vip": "false",
        "u_vip_alt": "true",
    }
    assert result.enrichment_data["mapped_fields"]["privileged"]["values"] == {
        "u_privileged_user": "0",
        "u_admin": "yes",
    }


@pytest.mark.asyncio
async def test_user_lookup_skips_without_http_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingAsyncClient(FakeAsyncClient):
        async def get(self, url: str, params: dict[str, object] | None = None):
            raise AssertionError("HTTP should not be called")

    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FailingAsyncClient)
    provider = servicenow_provider.__class__()

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(**{"enrichment.servicenow.user_table_enabled": "false"}),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data == {
        "status": "skipped",
        "reason": "ServiceNow user table is disabled",
    }


@pytest.mark.asyncio
async def test_user_lookup_skips_without_http_when_lookup_fields_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingAsyncClient(FakeAsyncClient):
        async def get(self, url: str, params: dict[str, object] | None = None):
            raise AssertionError("HTTP should not be called")

    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FailingAsyncClient)
    provider = servicenow_provider.__class__()

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(**{"enrichment.servicenow.user_query_field": ""}),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data == {
        "status": "skipped",
        "reason": "ServiceNow user lookup fields are blank",
    }


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
async def test_bulk_sync_skips_when_user_table_disabled() -> None:
    provider = servicenow_provider.__class__()

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=_settings(**{"enrichment.servicenow.user_table_enabled": False}),  # type: ignore[arg-type]
    )

    assert results == []


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


@pytest.mark.asyncio
async def test_bulk_sync_skips_only_malformed_provider_records(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class MixedRecordAsyncClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            params: dict[str, object] | None = None,
        ):
            assert url.endswith("/api/now/table/sys_user")
            return FakeResponse(
                200,
                {
                    "result": [
                        {
                            "sys_id": "sensitive-malformed-servicenow-record",
                            "email": ["not-a-scalar"],
                        },
                        {
                            "sys_id": "sn-user-valid",
                            "email": "valid@example.com",
                            "name": "Valid User",
                        },
                    ]
                },
            )

    monkeypatch.setattr(
        "app.services.enrichment.providers.servicenow.httpx.AsyncClient",
        MixedRecordAsyncClient,
    )
    provider = servicenow_provider.__class__()

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=_settings(
            **{
                "enrichment.servicenow.page_size": 2,
                "enrichment.servicenow.max_records": 2,
            }
        ),  # type: ignore[arg-type]
    )

    assert [result.cache_key for result in results] == ["user:valid@example.com"]
    assert (
        "ServiceNow bulk sync skipped malformed user records (count=1)"
        in caplog.messages
    )
    assert "sensitive-malformed-servicenow-record" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError, AttributeError])
async def test_bulk_sync_propagates_unexpected_record_processing_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    monkeypatch.setattr(
        "app.services.enrichment.providers.servicenow.httpx.AsyncClient",
        FakeAsyncClient,
    )
    provider = servicenow_provider.__class__()

    def raise_defect(*args, **kwargs):
        raise error_type("record processing defect")

    monkeypatch.setattr(provider, "_build_result", raise_defect)

    with pytest.raises(error_type, match="record processing defect"):
        await provider.bulk_sync(
            db=None,  # type: ignore[arg-type]
            settings=_settings(),  # type: ignore[arg-type]
        )
