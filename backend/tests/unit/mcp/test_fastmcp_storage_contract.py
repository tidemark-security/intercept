from __future__ import annotations

import importlib.util
from pathlib import Path

from packaging.requirements import Requirement


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _load_migration_module(filename: str):
    migration_path = BACKEND_ROOT / "db_migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    assert str(fastmcp.specifier) == "==3.4.4"
    assert str(key_value.specifier) == "==0.4.4"
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


def test_fastmcp_storage_migration_is_the_next_revision() -> None:
    migration = _load_migration_module("014_fastmcp_auth_storage.py")

    assert migration.revision == "014_fastmcp_auth_storage"
    assert migration.down_revision == "013_mcp_oauth"


def test_mcp_oauth_downgrade_only_drops_indexes_created_by_revision_013(monkeypatch) -> None:
    migration = _load_migration_module("013_mcp_oauth.py")
    dropped_indexes: list[tuple[str, str | None]] = []

    class RecordingOperations:
        def drop_index(self, name: str, *, table_name: str | None = None) -> None:
            dropped_indexes.append((name, table_name))

        def drop_table(self, _name: str) -> None:
            pass

    monkeypatch.setattr(migration, "op", RecordingOperations())
    migration.downgrade()

    assert ("ix_mcp_oauth_consents_user", "mcp_oauth_consents") not in dropped_indexes
    assert set(dropped_indexes) == {
        ("ix_mcp_oauth_tokens_expires_at", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_tokens_refresh_token_id", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_tokens_user_id", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_tokens_client_db_id", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_tokens_token_hash", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_tokens_id", "mcp_oauth_tokens"),
        ("ix_mcp_oauth_authorization_codes_expires_at", "mcp_oauth_authorization_codes"),
        ("ix_mcp_oauth_authorization_codes_user_id", "mcp_oauth_authorization_codes"),
        ("ix_mcp_oauth_authorization_codes_client_db_id", "mcp_oauth_authorization_codes"),
        ("ix_mcp_oauth_authorization_codes_code_hash", "mcp_oauth_authorization_codes"),
        ("ix_mcp_oauth_authorization_codes_id", "mcp_oauth_authorization_codes"),
        ("ix_mcp_oauth_consents_client_db_id", "mcp_oauth_consents"),
        ("ix_mcp_oauth_consents_user_id", "mcp_oauth_consents"),
        ("ix_mcp_oauth_consents_id", "mcp_oauth_consents"),
        ("ix_mcp_oauth_clients_client_id", "mcp_oauth_clients"),
        ("ix_mcp_oauth_clients_id", "mcp_oauth_clients"),
    }
