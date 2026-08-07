"""Add durable FastMCP dynamic-registration abuse controls.

Upgrade compatibility:
Pre-017 HTTPS CIMD client-store projections are deleted during upgrade. They are
cache-like copies of metadata that FastMCP refetches and validates from the
client-ID URL on use, so Alembic downgrade intentionally does not reconstruct
them. This cache cleanup is irreversible at the database level.

Revision ID: 017_mcp_dcr_abuse_controls
Revises: 016_soc_metrics_work_grain
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "017_mcp_dcr_abuse_controls"
down_revision: Union[str, None] = "016_soc_metrics_work_grain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_LOCAL_DCR_BACKFILL_SQL = """
INSERT INTO mcp_oauth_dcr_registrations (
    id,
    client_id,
    provider_mode,
    source_ip,
    created_at,
    expires_at,
    activated_at
)
SELECT
    md5('intercept-mcp-dcr-local:' || clients.client_id)::uuid,
    clients.client_id,
    'local',
    'legacy-upgrade-017',
    COALESCE(clients.created_at, NOW()),
    GREATEST(
        NOW() + INTERVAL '30 days',
        COALESCE(
            (
                SELECT MAX(tokens.expires_at)
                FROM mcp_oauth_tokens AS tokens
                WHERE tokens.client_db_id = clients.id
                  AND tokens.revoked_at IS NULL
                  AND tokens.expires_at > NOW()
            ),
            NOW() + INTERVAL '30 days'
        ),
        COALESCE(
            (
                SELECT MAX(codes.expires_at)
                FROM mcp_oauth_authorization_codes AS codes
                WHERE codes.client_db_id = clients.id
                  AND codes.consumed_at IS NULL
                  AND codes.expires_at > NOW()
            ),
            NOW() + INTERVAL '30 days'
        )
    ),
    NOW()
FROM mcp_oauth_clients AS clients
WHERE clients.revoked_at IS NULL
  AND clients.client_id !~* '^https://'
ON CONFLICT (client_id) DO NOTHING
"""


LEGACY_OIDC_DCR_BACKFILL_SQL = """
INSERT INTO mcp_oauth_dcr_registrations (
    id,
    client_id,
    provider_mode,
    source_ip,
    created_at,
    expires_at,
    activated_at
)
SELECT
    md5('intercept-mcp-dcr-oidc:' || key)::uuid,
    key,
    'oidc',
    'legacy-upgrade-017',
    NOW(),
    GREATEST(
        NOW() + INTERVAL '30 days',
        COALESCE(
            (
                SELECT MAX(native_state.expires_at)
                FROM fastmcp_oauth_kv AS native_state
                WHERE native_state.expires_at > NOW()
            ),
            NOW() + INTERVAL '30 days'
        )
    ),
    NOW()
FROM fastmcp_oauth_kv
WHERE collection = 'mcp-oauth-proxy-clients'
  AND (expires_at IS NULL OR expires_at > NOW())
  AND key !~* '^https://'
ON CONFLICT (client_id) DO NOTHING
"""


REMOVE_LEGACY_OIDC_CIMD_PROJECTIONS_SQL = """
DELETE FROM fastmcp_oauth_kv
WHERE collection = 'mcp-oauth-proxy-clients'
  AND key ~* '^https://'
"""


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_dcr_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=2048), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index(
        "ix_mcp_oauth_dcr_registrations_expiry",
        "mcp_oauth_dcr_registrations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_dcr_registrations_source_created",
        "mcp_oauth_dcr_registrations",
        ["source_ip", "created_at"],
        unique=False,
    )
    op.create_table(
        "mcp_oauth_authorization_capacity",
        sa.Column("reservation_id", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.String(length=2048), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("reservation_id"),
    )
    op.create_index(
        "ix_mcp_oauth_authorization_capacity_expiry",
        "mcp_oauth_authorization_capacity",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_oauth_authorization_capacity_client_expiry",
        "mcp_oauth_authorization_capacity",
        ["client_id", "expires_at"],
        unique=False,
    )
    # Before this ledger existed, local OAuth clients lived in the relational
    # client table and OIDC proxy clients lived in FastMCP's native KV
    # collection. Adopt that finite upgrade-time population explicitly so a
    # missing ledger row can fail closed forever after migration 017. CIMD
    # HTTPS client IDs remain untracked because the SDK validates them on use.
    op.execute(sa.text(LEGACY_OIDC_DCR_BACKFILL_SQL))
    # CIMD metadata is fetched and validated on use. Older FastMCP releases
    # persisted one client-store entry per attacker-controlled URL, so remove
    # those cache-like projections during adoption rather than carrying an
    # unbounded pre-017 population forward. This deletion is intentionally not
    # reversed by downgrade: FastMCP refetches and validates CIMD metadata on use.
    op.execute(sa.text(REMOVE_LEGACY_OIDC_CIMD_PROJECTIONS_SQL))
    # OIDC connected-client projections also appear in mcp_oauth_clients.
    # Insert native clients first so their provider mode wins the unique-ID
    # conflict and their KV cleanup remains reachable.
    op.execute(sa.text(LEGACY_LOCAL_DCR_BACKFILL_SQL))


def downgrade() -> None:
    # HTTPS CIMD projections deleted during upgrade are refetchable caches and
    # are intentionally not reconstructed here. See the module upgrade note.
    op.drop_index(
        "ix_mcp_oauth_authorization_capacity_client_expiry",
        table_name="mcp_oauth_authorization_capacity",
    )
    op.drop_index(
        "ix_mcp_oauth_authorization_capacity_expiry",
        table_name="mcp_oauth_authorization_capacity",
    )
    op.drop_table("mcp_oauth_authorization_capacity")
    op.drop_index(
        "ix_mcp_oauth_dcr_registrations_source_created",
        table_name="mcp_oauth_dcr_registrations",
    )
    op.drop_index(
        "ix_mcp_oauth_dcr_registrations_expiry",
        table_name="mcp_oauth_dcr_registrations",
    )
    op.drop_table("mcp_oauth_dcr_registrations")
