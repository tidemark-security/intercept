from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from mcp.server.auth.provider import TokenError
from sqlalchemy import Select, func, select

from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.oidc_provider import (
    CONNECTED_CLIENT_REFERENCE_COLLECTION,
    InterceptOIDCProxy,
    OIDCIdentityError,
    oidc_authorize_parameters,
    resolve_upstream_oidc_scopes,
)
from app.models.enums import UserRole, UserStatus
from app.models.models import (
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    UserAccount,
)
from app.services.oidc_service import OIDCAuthenticationError, OIDCIdentityPolicy


def test_google_scope_translation_keeps_mcp_scope_local() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        configured_scopes="openid email profile",
    )

    assert scopes == ["openid", "email", "profile"]
    assert MCP_ACCESS_SCOPE not in scopes
    assert oidc_authorize_parameters(
        "https://accounts.google.com/.well-known/openid-configuration"
    ) == {"access_type": "offline", "prompt": "consent"}


def test_entra_scope_translation_adds_offline_access_once() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url=(
            "https://login.microsoftonline.com/tenant/v2.0/"
            ".well-known/openid-configuration"
        ),
        configured_scopes="openid profile offline_access email offline_access",
    )

    assert scopes == ["openid", "profile", "offline_access", "email"]
    assert MCP_ACCESS_SCOPE not in scopes


def test_generic_scope_translation_uses_exact_configured_scopes() -> None:
    scopes = resolve_upstream_oidc_scopes(
        discovery_url="https://id.example/.well-known/openid-configuration",
        configured_scopes="openid custom.read email",
    )

    assert scopes == ["openid", "custom.read", "email"]
    assert oidc_authorize_parameters(
        "https://id.example/.well-known/openid-configuration"
    ) == {}


def test_proxy_scope_hooks_never_forward_mcp_access() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._intercept_upstream_scopes = ["openid", "email", "profile"]

    assert proxy._prepare_scopes_for_token_exchange([MCP_ACCESS_SCOPE]) == [
        "openid",
        "email",
        "profile",
    ]
    assert proxy._prepare_scopes_for_upstream_refresh([MCP_ACCESS_SCOPE]) == [
        "openid",
        "email",
        "profile",
    ]
    assert proxy._translate_scopes_from_idp(["openid", "email"]) == [
        MCP_ACCESS_SCOPE
    ]


class _Session:
    def __init__(self, user=None) -> None:
        self.user = user
        self.committed = False

    async def get(self, _model, user_id):
        return self.user if self.user is not None and self.user.id == user_id else None

    async def commit(self) -> None:
        self.committed = True


def _session_factory(session: _Session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.mark.asyncio
async def test_proxy_normalizes_verified_id_token_through_oidc_service() -> None:
    user = SimpleNamespace(
        id=uuid4(),
        username="person@example.com",
        role=SimpleNamespace(value="ANALYST"),
    )
    verified = AccessToken(
        token="id-token",
        client_id="intercept-oidc-client",
        scopes=[],
        claims={
            "sub": "provider-subject",
            "email": "person@example.com",
            "preferred_username": "person@example.com",
        },
    )
    session = _Session()
    oidc_service = SimpleNamespace(find_or_create_user=AsyncMock(return_value=user))
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._token_validator = SimpleNamespace(verify_token=AsyncMock(return_value=verified))
    proxy._intercept_session_factory = _session_factory(session)
    proxy._intercept_oidc_service = oidc_service
    identity_policy = OIDCIdentityPolicy(
        jit_provisioning=False,
        default_role="AUDITOR",
        role_claim_path="groups",
        role_mapping={"security-auditors": "AUDITOR"},
        trusted_auto_link_issuers=("https://issuer.example",),
    )
    proxy._intercept_identity_policy = identity_policy
    proxy.oidc_config = SimpleNamespace(issuer="https://issuer.example")

    claims = await proxy._extract_upstream_claims({"id_token": "id-token"})

    oidc_service.find_or_create_user.assert_awaited_once_with(
        session,
        claims=verified.claims,
        issuer="https://issuer.example",
        identity_policy=identity_policy,
    )
    assert claims == {
        "intercept_user_id": str(user.id),
        "auth_source": "oidc",
        "oidc_issuer": "https://issuer.example",
        "oidc_subject": "provider-subject",
    }
    assert session.committed is True


@pytest.mark.asyncio
async def test_proxy_rejects_token_response_without_validated_id_token() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._token_validator = SimpleNamespace(verify_token=AsyncMock(return_value=None))

    with pytest.raises(OIDCIdentityError):
        await proxy._extract_upstream_claims({"id_token": "invalid"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_error",
    [
        OIDCIdentityError("OIDC id_token validation failed"),
        OIDCAuthenticationError("OIDC-linked user account is not active"),
    ],
)
async def test_authorization_code_identity_failure_is_native_error_and_cleans_tokens(
    monkeypatch: pytest.MonkeyPatch,
    identity_error: Exception,
) -> None:
    upstream_store = SimpleNamespace(put=AsyncMock(), delete=AsyncMock())

    async def fastmcp_exchange(proxy, _client, _authorization_code):
        await proxy._upstream_token_store.put(
            key="persisted-before-identity-hook",
            value=SimpleNamespace(access_token="upstream-secret"),
            ttl=300,
        )
        raise identity_error

    monkeypatch.setattr(OIDCProxy, "exchange_authorization_code", fastmcp_exchange)
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._upstream_token_store = upstream_store

    with pytest.raises(TokenError) as exc_info:
        await proxy.exchange_authorization_code(
            SimpleNamespace(client_id="vscode-client"),
            SimpleNamespace(code="one-use-code"),
        )

    assert exc_info.value.error == "invalid_grant"
    assert "identity" in str(exc_info.value.error_description).lower()
    upstream_store.delete.assert_awaited_once_with(
        key="persisted-before-identity-hook"
    )


@pytest.mark.asyncio
async def test_proxy_returns_reference_token_with_local_identity_not_upstream_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, status=UserStatus.ACTIVE)
    session = _Session(user)
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=["openid", "email"],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
                "oidc_issuer": "https://issuer.example",
                "oidc_subject": "provider-subject",
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {"client_id": "vscode-client", "jti": "reference-id"}
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = _session_factory(session)
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-set-id")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    proxy.get_client = AsyncMock(return_value=None)
    proxy._record_connected_client_projection = AsyncMock()

    result = await proxy.load_access_token("fastmcp-reference-token")

    assert result is not None
    assert result.token == "fastmcp-reference-token"
    assert result.client_id == "vscode-client"
    assert result.scopes == [MCP_ACCESS_SCOPE]
    assert result.resource == "https://intercept.example/mcp/streamable/"
    assert result.claims["intercept_user_id"] == str(user_id)
    assert result.claims["auth_source"] == "oidc"
    assert "upstream-provider-secret" not in repr(result)


@pytest.mark.asyncio
async def test_validated_reference_updates_token_free_connected_client_projection(
    monkeypatch: pytest.MonkeyPatch,
    session_maker,
) -> None:
    user = UserAccount(
        username="projected.oidc@example.com",
        email="projected.oidc@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="projected-provider-subject",
    )
    async with session_maker() as db:
        db.add(user)
        await db.commit()
    user_id = user.id
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=["openid", "email"],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {
            "client_id": "vscode-client",
            "jti": "reference-id",
            "exp": 2_000_000_000,
        }
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = session_maker
    proxy.get_client = AsyncMock(
        return_value=SimpleNamespace(
            client_id="vscode-client",
            client_name="VS Code",
            client_uri="https://code.visualstudio.com",
            logo_uri=None,
            redirect_uris=["http://127.0.0.1:4567/callback"],
            scope=MCP_ACCESS_SCOPE,
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
            contacts=None,
            jwks_uri=None,
            cimd_document=None,
        )
    )
    proxy._jti_mapping_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(upstream_token_id="upstream-set-id")
        )
    )
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=2_000_000_000,
                refresh_token_expires_at=2_100_000_000,
            )
        )
    )
    proxy._client_storage = SimpleNamespace(put=AsyncMock())
    monkeypatch.setattr("app.mcp.oidc_provider.time.time", lambda: 1_900_000_000)

    result = await proxy.load_access_token("fastmcp-reference-token")

    assert result is not None
    async with session_maker() as db:
        client = (await db.execute(select(MCPOAuthClient))).scalar_one()
        consent = (await db.execute(select(MCPOAuthConsent))).scalar_one()
        grant_reference = (
            await db.execute(select(MCPOAuthProviderGrantReference))
        ).scalar_one()
    assert client.client_name == "VS Code"
    assert client.client_metadata == {"registration_source": "dcr"}
    assert consent.user_id == user_id
    assert consent.provider_mode == "oidc"
    assert (
        consent.provider_reference_hash
        == "1b7e95116aff9dc9c89bcf5b02e1ed2d8596841a7cd7e14c5edb55c3259cd901"
    )
    assert consent.last_used_at is not None
    assert grant_reference.consent_id == consent.id
    assert grant_reference.provider_reference_hash == consent.provider_reference_hash
    assert grant_reference.last_used_at is not None
    assert "upstream-provider-secret" not in repr(client)
    assert "upstream-provider-secret" not in repr(consent)
    assert "upstream-provider-secret" not in repr(grant_reference)
    proxy._client_storage.put.assert_awaited_once()
    native_write = proxy._client_storage.put.await_args.kwargs
    assert native_write["collection"] == CONNECTED_CLIENT_REFERENCE_COLLECTION
    assert native_write["value"] == {
        "user_id": str(user_id),
        "client_id": "vscode-client",
        "jti": "reference-id",
        "upstream_token_id": "upstream-set-id",
    }
    assert native_write["ttl"] == 200_000_000


@pytest.mark.asyncio
async def test_connected_client_projection_is_idempotent_across_workers(
    session_maker,
) -> None:
    user = UserAccount(
        username="oidc.projection@example.com",
        email="oidc.projection@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="provider-subject",
    )
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    client_info = SimpleNamespace(
        client_name="VS Code",
        client_uri="https://code.visualstudio.com",
        logo_uri=None,
        redirect_uris=["http://127.0.0.1:4567/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        contacts=[],
        jwks_uri=None,
        cimd_document=None,
    )
    proxy = object.__new__(InterceptOIDCProxy)

    class _SelectBarrier:
        def __init__(self) -> None:
            self.arrivals = 0
            self.ready = asyncio.Event()

        async def wait(self) -> None:
            self.arrivals += 1
            if self.arrivals == 2:
                self.ready.set()
            await self.ready.wait()

    class _WorkerSession:
        def __init__(self, db, barrier: _SelectBarrier) -> None:
            self._db = db
            self._barrier = barrier
            self._synchronized = False

        async def execute(self, statement):
            result = await self._db.execute(statement)
            if isinstance(statement, Select) and not self._synchronized:
                self._synchronized = True
                await self._barrier.wait()
            return result

        def __getattr__(self, name):
            return getattr(self._db, name)

    barrier = _SelectBarrier()

    async def record_from_worker() -> None:
        async with session_maker() as db:
            await proxy._record_connected_client_projection(
                _WorkerSession(db, barrier),
                user_id=user.id,
                client_id="vscode-client",
                client_info=client_info,
                reference_hash="same-native-token-family",
            )
            await db.commit()

    await asyncio.wait_for(
        asyncio.gather(record_from_worker(), record_from_worker()),
        timeout=5,
    )

    async with session_maker() as db:
        assert await db.scalar(select(func.count()).select_from(MCPOAuthClient)) == 1
        assert await db.scalar(select(func.count()).select_from(MCPOAuthConsent)) == 1
        assert (
            await db.scalar(
                select(func.count()).select_from(MCPOAuthProviderGrantReference)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_revoke_projected_client_invalidates_native_token_family() -> None:
    user_id = uuid4()
    reference_hash = (
        "1b7e95116aff9dc9c89bcf5b02e1ed2d8596841a7cd7e14c5edb55c3259cd901"
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._client_storage = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "user_id": str(user_id),
                "client_id": "vscode-client",
                "jti": "reference-id",
                "upstream_token_id": "upstream-set-id",
            }
        ),
        delete=AsyncMock(return_value=True),
    )
    proxy._jti_mapping_store = SimpleNamespace(delete=AsyncMock(return_value=True))
    proxy._upstream_token_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                access_token="upstream-access-secret",
                refresh_token="upstream-refresh-secret",
                client_id="vscode-client",
                scope="openid email",
            )
        ),
        delete=AsyncMock(return_value=True),
    )
    proxy.revoke_token = AsyncMock()

    revoked = await proxy.revoke_projected_client(
        user_id=user_id,
        provider_reference_hash=reference_hash,
    )

    assert revoked is True
    assert [
        call.args[0].token for call in proxy.revoke_token.await_args_list
    ] == ["upstream-access-secret", "upstream-refresh-secret"]
    proxy._jti_mapping_store.delete.assert_awaited_once_with(key="reference-id")
    proxy._upstream_token_store.delete.assert_awaited_once_with(
        key="upstream-set-id"
    )
    proxy._client_storage.delete.assert_awaited_once_with(
        key=reference_hash,
        collection=CONNECTED_CLIENT_REFERENCE_COLLECTION,
    )


@pytest.mark.asyncio
async def test_revoke_projected_client_rejects_another_users_reference() -> None:
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._client_storage = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "user_id": str(uuid4()),
                "client_id": "vscode-client",
                "jti": "reference-id",
                "upstream_token_id": "upstream-set-id",
            }
        ),
        delete=AsyncMock(),
    )
    proxy._upstream_token_store = SimpleNamespace(delete=AsyncMock())
    proxy._jti_mapping_store = SimpleNamespace(delete=AsyncMock())

    revoked = await proxy.revoke_projected_client(
        user_id=uuid4(),
        provider_reference_hash="reference-hash",
    )

    assert revoked is False
    proxy._upstream_token_store.delete.assert_not_awaited()
    proxy._jti_mapping_store.delete.assert_not_awaited()
    proxy._client_storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_rejects_reference_when_local_user_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = _Session(SimpleNamespace(id=user_id, status=UserStatus.DISABLED))
    upstream_result = AccessToken(
        token="upstream-provider-secret",
        client_id="intercept-oidc-app",
        scopes=[],
        claims={
            "upstream_claims": {
                "intercept_user_id": str(user_id),
                "auth_source": "oidc",
            }
        },
    )
    monkeypatch.setattr(
        OIDCProxy,
        "load_access_token",
        AsyncMock(return_value=upstream_result),
    )
    proxy = object.__new__(InterceptOIDCProxy)
    proxy._jwt_issuer = SimpleNamespace(
        verify_token=lambda _token: {"client_id": "vscode-client", "jti": "reference-id"}
    )
    proxy._resource_url = "https://intercept.example/mcp/streamable/"
    proxy._intercept_session_factory = _session_factory(session)

    assert await proxy.load_access_token("fastmcp-reference-token") is None
