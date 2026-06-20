import httpx
import pytest

from app.services.enrichment.base import EnrichmentResult
from app.services.enrichment.providers.servicenow import servicenow_provider
from app.services.enrichment.service import enrichment_service


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.auth = kwargs.get("auth")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        assert self.auth == ("svc-user", "svc-pass")
        assert params is not None
        if url.endswith("/api/now/table/sys_user"):
            assert params["sysparm_query"] == "user_name=alice@example.com^active=true"
            return FakeResponse(
                {
                    "result": [
                        {
                            "sys_id": {"value": "sn-user-1"},
                            "user_name": {"display_value": "alice"},
                            "email": {"display_value": "alice@example.com"},
                            "name": {"display_value": "Alice Analyst"},
                            "title": {"display_value": "CISO"},
                            "department": {"display_value": "Security"},
                            "vip": {"value": "true"},
                            "u_privileged_user": {"value": "1"},
                            "active": {"value": "true"},
                        }
                    ]
                }
            )
        if url.endswith("/api/now/table/cmdb_ci"):
            assert params["sysparm_query"] == "name=dc01"
            return FakeResponse(
                {
                    "result": [
                        {
                            "sys_id": {"value": "sn-ci-1"},
                            "name": {"display_value": "dc01"},
                            "fqdn": {"display_value": "dc01.example.com"},
                            "ip_address": {"display_value": "10.0.0.5"},
                            "criticality": {"display_value": "critical"},
                            "u_privileged_system": {"value": "true"},
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected ServiceNow lookup: {url} {params}")


class CMDBFakeAsyncClient:
    requests: list[dict[str, object]] = []
    responses: dict[str, list[dict[str, object]]] = {}
    fail_on_query: str | None = None

    def __init__(self, *args, **kwargs):
        self.auth = kwargs.get("auth")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        assert self.auth == ("svc-user", "svc-pass")
        assert url.endswith("/api/now/table/cmdb_ci")
        assert params is not None
        query = str(params["sysparm_query"])
        self.requests.append(dict(params))
        if query == self.fail_on_query:
            raise httpx.ConnectError("network unavailable", request=httpx.Request("GET", url))
        return FakeResponse({"result": self.responses.get(query, [])})


def _settings(**overrides: object) -> StubSettings:
    values: dict[str, object] = {
            "enrichment.servicenow.instance_url": "https://example.service-now.com/",
            "enrichment.servicenow.username": "svc-user",
            "enrichment.servicenow.password": "svc-pass",
            "enrichment.servicenow.table": "sys_user",
            "enrichment.servicenow.lookup_query_template": "user_name={value}^active=true",
            "enrichment.servicenow.user_vip_field": "vip",
            "enrichment.servicenow.user_privileged_field": "u_privileged_user",
            "enrichment.servicenow.cmdb_table": "cmdb_ci",
            "enrichment.servicenow.cmdb_query_field": "name",
            "enrichment.servicenow.cmdb_criticality_field": "criticality",
            "enrichment.servicenow.cmdb_privileged_field": "u_privileged_system",
        }
    values.update(overrides)
    return StubSettings(values)


def _cmdb_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "sys_id": {"value": "sn-ci-1"},
        "name": {"display_value": "dc01"},
        "fqdn": {"display_value": "dc01.example.com"},
        "ip_address": {"display_value": "10.0.0.5"},
        "sys_class_name": {"display_value": "cmdb_ci_server"},
        "criticality": {"display_value": "critical"},
        "u_privileged_system": {"value": "true"},
    }
    record.update(overrides)
    return record


def test_can_enrich_and_build_cache_key() -> None:
    provider = servicenow_provider.__class__()

    assert provider.can_enrich({"type": "internal_actor", "user_id": "Alice@Example.com"})
    assert (
        provider.build_cache_key({"type": "internal_actor", "user_id": "Alice@Example.com"})
        == "user:alice@example.com"
    )
    assert provider.can_enrich({"type": "system", "hostname": "DC01"})
    assert provider.build_cache_key({"type": "system", "hostname": "DC01"}) == "system:dc01"
    assert provider.build_cache_key({"type": "system", "hostname": "DC01", "cmdb_id": "CI-1"}) == "system:dc01"
    assert not provider.can_enrich({"type": "external_actor", "name": "Alice"})


@pytest.mark.asyncio
async def test_enrich_fetches_vip_and_privileged_user(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice@example.com"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "servicenow"
    assert result.cache_key == "user:alice@example.com"
    assert result.enrichment_data["display_name"] == "Alice Analyst"
    assert result.enrichment_data["is_vip"] is True
    assert result.enrichment_data["is_privileged"] is True
    alias_types = {alias.alias_type for alias in result.aliases}
    assert {"servicenow_sys_id", "email", "username", "display_name"}.issubset(alias_types)


@pytest.mark.asyncio
async def test_preview_fetches_cmdb_system(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", FakeAsyncClient)

    result = await provider.preview(
        config={
            "instance_url": "https://example.service-now.com",
            "username": "svc-user",
            "password": "svc-pass",
        },
        item={"type": "system", "hostname": "dc01"},
    )

    assert result.cache_key == "system:dc01"
    assert result.enrichment_data["name"] == "dc01"
    assert result.enrichment_data["is_critical"] is True
    assert result.enrichment_data["is_privileged"] is True


@pytest.mark.asyncio
async def test_cmdb_lookup_uses_deterministic_identifier_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    CMDBFakeAsyncClient.requests = []
    CMDBFakeAsyncClient.fail_on_query = None
    CMDBFakeAsyncClient.responses = {
        "ip_address=10.0.0.5": [_cmdb_record()],
    }
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", CMDBFakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "system", "hostname": "missing-host", "ip_address": "10.0.0.5", "cmdb_id": "CI-123"},
        entity_type="alert",
        entity_id=1,
    )

    assert [request["sysparm_query"] for request in CMDBFakeAsyncClient.requests] == [
        "name=missing-host",
        "fqdn=missing-host",
        "ip_address=10.0.0.5",
    ]
    assert result.enrichment_data["status"] == "matched"
    assert result.enrichment_data["matched_identifier"] == {
        "source": "ip_address",
        "field": "ip_address",
        "value": "10.0.0.5",
    }
    assert result.enrichment_data["source_table"] == "cmdb_ci"
    assert result.enrichment_data["record_id"] == "sn-ci-1"
    assert result.enrichment_data["record_link"].endswith("/nav_to.do?uri=/cmdb_ci.do?sys_id=sn-ci-1")
    assert result.enrichment_data["ci_class"] == "cmdb_ci_server"
    assert result.enrichment_data["privilege_fields"] == {"u_privileged_system": "true"}


@pytest.mark.asyncio
async def test_cmdb_lookup_uses_configured_identifier_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    CMDBFakeAsyncClient.requests = []
    CMDBFakeAsyncClient.fail_on_query = None
    CMDBFakeAsyncClient.responses = {
        "asset_tag=asset-42": [_cmdb_record(sys_id={"value": "sn-ci-42"})],
    }
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", CMDBFakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(**{"enrichment.servicenow.cmdb_query_field": "asset_tag,serial_number"}),  # type: ignore[arg-type]
        item={"type": "system", "cmdb_id": "asset-42"},
        entity_type="alert",
        entity_id=1,
    )

    assert CMDBFakeAsyncClient.requests[0]["sysparm_query"] == "asset_tag=asset-42"
    assert result.enrichment_data["status"] == "matched"
    assert result.enrichment_data["matched_identifier"] == {
        "source": "cmdb_id",
        "field": "asset_tag",
        "value": "asset-42",
    }


@pytest.mark.asyncio
async def test_cmdb_lookup_returns_non_terminal_missing_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    CMDBFakeAsyncClient.requests = []
    CMDBFakeAsyncClient.responses = {}
    CMDBFakeAsyncClient.fail_on_query = None
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", CMDBFakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "system", "hostname": "unknown"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data["status"] == "not_found"
    assert result.enrichment_data["error"] == "CMDB item not found"
    assert result.aliases == []


@pytest.mark.asyncio
async def test_cmdb_lookup_returns_non_terminal_ambiguous_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    CMDBFakeAsyncClient.requests = []
    CMDBFakeAsyncClient.fail_on_query = None
    CMDBFakeAsyncClient.responses = {
        "name=dc01": [_cmdb_record(sys_id={"value": "sn-ci-1"}), _cmdb_record(sys_id={"value": "sn-ci-2"})],
    }
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", CMDBFakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "system", "hostname": "dc01"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data["status"] == "ambiguous"
    assert result.enrichment_data["record_count"] == 2
    assert "multiple records" in result.enrichment_data["error"]
    assert result.aliases == []


@pytest.mark.asyncio
async def test_cmdb_lookup_returns_error_payload_for_failed_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = servicenow_provider.__class__()
    CMDBFakeAsyncClient.requests = []
    CMDBFakeAsyncClient.responses = {}
    CMDBFakeAsyncClient.fail_on_query = "name=dc01"
    monkeypatch.setattr("app.services.enrichment.providers.servicenow.httpx.AsyncClient", CMDBFakeAsyncClient)

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "system", "hostname": "dc01"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.enrichment_data["status"] == "lookup_error"
    assert "CMDB lookup failed" in result.enrichment_data["error"]
    assert result.aliases == []


def test_service_applies_successful_cmdb_system_fields_independently() -> None:
    item = {"type": "system", "hostname": "dc01", "is_privileged": False}
    result = EnrichmentResult(
        provider_id="servicenow",
        cache_key="system:dc01",
        enrichment_data={
            "status": "matched",
            "record_id": "sn-ci-1",
            "ip_address": "10.0.0.5",
            "is_privileged": True,
            "is_critical": True,
        },
    )

    enrichment_service._apply_system_enrichment_fields(item, result)

    assert item["is_privileged"] is True
    assert item["is_critical"] is True
    assert item["cmdb_id"] == "sn-ci-1"
    assert item["ip_address"] == "10.0.0.5"
