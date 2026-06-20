import pytest

from app.services.enrichment.providers.servicenow import servicenow_provider


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


def _settings() -> StubSettings:
    return StubSettings(
        {
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
    )


def test_can_enrich_and_build_cache_key() -> None:
    provider = servicenow_provider.__class__()

    assert provider.can_enrich({"type": "internal_actor", "user_id": "Alice@Example.com"})
    assert (
        provider.build_cache_key({"type": "internal_actor", "user_id": "Alice@Example.com"})
        == "user:alice@example.com"
    )
    assert provider.can_enrich({"type": "system", "hostname": "DC01"})
    assert provider.build_cache_key({"type": "system", "hostname": "DC01"}) == "system:dc01"
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
