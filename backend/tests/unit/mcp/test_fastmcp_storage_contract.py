from __future__ import annotations

from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _requirement_named(name: str) -> Requirement:
    requirements = [
        Requirement(line)
        for line in (BACKEND_ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-r"))
    ]
    return next(requirement for requirement in requirements if requirement.name == name)


def test_fastmcp_auth_storage_dependencies_are_pinned() -> None:
    fastmcp = _requirement_named("fastmcp")
    key_value = _requirement_named("py-key-value-aio")

    for requirement in (fastmcp, key_value):
        specifier, = requirement.specifier
        assert specifier.operator == "=="
        assert "*" not in specifier.version
    assert Version(next(iter(fastmcp.specifier)).version) >= Version("4.2.4")
    assert key_value.extras == {"postgresql", "wrappers-encryption"}


def test_pending_authorization_model_matches_the_local_oauth_handoff() -> None:
    from app.models.models import MCPOAuthPendingAuthorization

    table = MCPOAuthPendingAuthorization.__table__

    assert table.name == "mcp_oauth_pending_authorizations"
    assert set(table.columns) == {
        table.c.id,
        table.c.client_db_id,
        table.c.state,
        table.c.scopes,
        table.c.code_challenge,
        table.c.redirect_uri,
        table.c.redirect_uri_provided_explicitly,
        table.c.resource,
        table.c.expires_at,
        table.c.consumed_at,
        table.c.created_at,
    }
    assert table.c.client_db_id.foreign_keys
    assert {index.name for index in table.indexes} >= {
        "ix_mcp_oauth_pending_authorizations_id",
        "ix_mcp_oauth_pending_authorizations_client_db_id",
        "ix_mcp_oauth_pending_authorizations_expires_at",
    }


def test_consent_projection_identifies_native_provider_without_storing_tokens() -> None:
    from app.models.models import MCPOAuthConsent, MCPOAuthProviderGrantReference

    table = MCPOAuthConsent.__table__

    assert table.c.provider_mode.default.arg == "local"
    assert table.c.provider_reference_hash.nullable is True
    assert table.c.provider_reference_hash.type.length == 128
    assert "provider_reference" not in table.c
    assert table.c.last_used_at.nullable is True
    assert "ix_mcp_oauth_consents_provider_reference" in {
        index.name for index in table.indexes
    }

    reference_table = MCPOAuthProviderGrantReference.__table__
    assert set(reference_table.columns.keys()) == {
        "id",
        "consent_id",
        "provider_reference_hash",
        "created_at",
        "last_used_at",
        "revoked_at",
    }
    assert "upstream_token" not in reference_table.columns
    assert reference_table.c.provider_reference_hash.type.length == 128
