import pytest

from app.services.enrichment.providers.ldap_provider import ldap_provider


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


class FakeAttribute:
    def __init__(self, value):
        self.value = value


class FakeEntry:
    def __init__(self, **attributes):
        for key, value in attributes.items():
            setattr(self, key, FakeAttribute(value))


class FakeConnection:
    def __init__(self, batches):
        self._batches = list(batches)
        self.entries = []
        self.result = {}
        self.search_calls = []

    def search(self, search_base, search_filter, attributes=None, paged_size=None, paged_cookie=None):
        self.search_calls.append(
            {
                "search_base": search_base,
                "search_filter": search_filter,
                "paged_size": paged_size,
                "paged_cookie": paged_cookie,
            }
        )
        if not self._batches:
            self.entries = []
            self.result = {"controls": {}}
            return True
        current = self._batches.pop(0)
        self.entries = current["entries"]
        cookie = current.get("cookie")
        self.result = {"controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": cookie}}}}
        return True

    def unbind(self):
        return True


def _settings() -> StubSettings:
    return StubSettings(
        {
            "enrichment.ldap.url": "ldaps://directory.example.com",
            "enrichment.ldap.bind_dn": "cn=svc,dc=example,dc=com",
            "enrichment.ldap.bind_password": "secret",
            "enrichment.ldap.search_base": "dc=example,dc=com",
            "enrichment.ldap.use_ssl": True,
            "enrichment.ldap.user_search_filter": "(|(sAMAccountName={uid})(mail={value}))",
        }
    )


def test_can_enrich_and_build_cache_key() -> None:
    item = {"type": "internal_actor", "user_id": "Alice@Example.com"}
    assert ldap_provider.can_enrich(item)
    assert ldap_provider.build_cache_key(item) == "user:alice@example.com"
    assert not ldap_provider.can_enrich({"type": "internal_actor"})


def test_build_user_search_filter_supports_value_and_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ldap_provider.__class__()
    monkeypatch.setattr(provider, "_escape_identifier", lambda identifier: "alice\\2a")

    search_filter = provider._build_user_search_filter("(|(sAMAccountName={uid})(mail={value}))", "alice*")

    assert search_filter == "(|(sAMAccountName=alice\\2a)(mail=alice\\2a))"


@pytest.mark.asyncio
async def test_enrich_returns_ldap_user(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ldap_provider.__class__()
    entry = FakeEntry(
        objectGUID=b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10",
        distinguishedName="CN=Alice Analyst,OU=Users,DC=example,DC=com",
        displayName="Alice Analyst",
        givenName="Alice",
        sn="Analyst",
        mail="alice@example.com",
        userPrincipalName="alice@example.com",
        sAMAccountName="alice",
        employeeID="E123",
        title="Security Analyst",
        department="SOC",
        company="Tidemark",
        physicalDeliveryOfficeName="HQ",
        telephoneNumber="+1-555-0110",
        mobile="+1-555-0100",
        manager="CN=Morgan Manager,OU=Users,DC=example,DC=com",
    )
    fake_connection = FakeConnection([{"entries": [entry], "cookie": None}])
    monkeypatch.setattr(provider, "_connect", lambda url, bind_dn, bind_password, use_ssl: fake_connection)
    monkeypatch.setattr(provider, "_escape_identifier", lambda identifier: identifier.replace("*", "\\2a"))

    result = await provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
        item={"type": "internal_actor", "user_id": "alice*"},
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "ldap"
    assert result.cache_key == "user:alice*"
    assert result.enrichment_data["display_name"] == "Alice Analyst"
    assert result.enrichment_data["manager_cn"] == "Morgan Manager"
    assert fake_connection.search_calls[0]["search_filter"] == "(|(sAMAccountName=alice\\2a)(mail=alice\\2a))"


@pytest.mark.asyncio
async def test_bulk_sync_returns_ldap_results(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ldap_provider.__class__()
    first_entry = FakeEntry(
        objectGUID=b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10",
        displayName="Alice Analyst",
        mail="alice@example.com",
        userPrincipalName="alice@example.com",
        sAMAccountName="alice",
    )
    second_entry = FakeEntry(
        objectGUID=b"\x10\x0f\x0e\r\x0c\x0b\n\t\x08\x07\x06\x05\x04\x03\x02\x01",
        displayName="Bob Builder",
        mail="bob@example.com",
        userPrincipalName="bob@example.com",
        sAMAccountName="bob",
    )
    fake_connection = FakeConnection(
        [
            {"entries": [first_entry], "cookie": b"next-page"},
            {"entries": [second_entry], "cookie": None},
        ]
    )
    monkeypatch.setattr(provider, "_connect", lambda url, bind_dn, bind_password, use_ssl: fake_connection)

    results = await provider.bulk_sync(
        db=None,  # type: ignore[arg-type]
        settings=_settings(),  # type: ignore[arg-type]
    )

    assert len(results) == 2
    assert results[0].cache_key == "user:alice@example.com"
    assert results[1].cache_key == "user:bob@example.com"
    assert fake_connection.search_calls[0]["paged_size"] == 500
    assert fake_connection.search_calls[1]["paged_cookie"] == b"next-page"