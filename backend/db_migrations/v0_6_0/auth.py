"""Migrate account credentials, login requests and authentication ledgers for v0.6.0."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from db_migrations.cron_utils import schedule_cron_job, unschedule_cron_job


ADMIN_LEGACY_SCOPES = '["api:admin", "api:read", "api:write", "mcp:access"]'
ANALYST_LEGACY_SCOPES = '["api:read", "api:write", "mcp:access"]'
AUDITOR_LEGACY_SCOPES = '["api:read", "mcp:access"]'


CONSTRAINT_NAME = "ck_user_accounts_oidc_identity_pair"
OIDC_IDENTITY_PAIR_EXPRESSION = (
    "(oidc_issuer IS NULL AND oidc_subject IS NULL) OR "
    "(oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL "
    "AND length(btrim(oidc_issuer, E' \\011\\012\\013\\014\\015')) > 0 "
    "AND length(btrim(oidc_subject, E' \\011\\012\\013\\014\\015')) > 0)"
)


def _has_column(table: str, column: str) -> bool:
    return op.get_bind().scalar(
        sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table AND column_name = :column
            )
        """),
        {"table": table, "column": column},
    )


def add_key_scopes() -> None:
    if _has_column("api_keys", "scopes"):
        return  # Fresh installs receive the column from 001 metadata creation.

    op.add_column(
        "api_keys",
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Legacy keys inherited their owner's authority. Preserve that behavior
    # without introducing a stored scope above the owner's current role ceiling.
    # An unknown role or orphaned key remains NULL so the NOT NULL transition
    # fails closed instead of guessing at a safe permission set.
    op.execute(
        sa.text(
            """
            UPDATE api_keys AS api_key
            SET scopes = CASE CAST(owner.role AS text)
                WHEN 'ADMIN' THEN CAST(:admin_scopes AS jsonb)
                WHEN 'ANALYST' THEN CAST(:analyst_scopes AS jsonb)
                WHEN 'AUDITOR' THEN CAST(:auditor_scopes AS jsonb)
            END
            FROM user_accounts AS owner
            WHERE owner.id = api_key.user_id
              AND api_key.scopes IS NULL
            """
        ).bindparams(
            admin_scopes=ADMIN_LEGACY_SCOPES,
            analyst_scopes=ANALYST_LEGACY_SCOPES,
            auditor_scopes=AUDITOR_LEGACY_SCOPES,
        )
    )
    op.alter_column("api_keys", "scopes", nullable=False)


def remove_key_scopes() -> None:
    if not _has_column("api_keys", "scopes"):
        return

    bind = op.get_bind()
    # Keep the row check and destructive schema change atomic with respect to
    # API-key creation. ALTER TABLE will take this lock too; acquiring it first
    # closes the gap between the safety check and dropping the column.
    bind.execute(sa.text("LOCK TABLE api_keys IN ACCESS EXCLUSIVE MODE"))
    has_api_keys = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM api_keys)")
    ).scalar_one()
    if has_api_keys:
        raise RuntimeError(
            "Cannot downgrade v0.6.0: api_keys contains rows. "
            "Dropping explicit scopes could widen existing keys to their "
            "owner's role authority after a later re-upgrade. Revoke and "
            "delete every API key before downgrading."
        )

    op.drop_column("api_keys", "scopes")


def _constraint_exists() -> bool:
    result = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = to_regclass('user_accounts')"
        ),
        {"constraint_name": CONSTRAINT_NAME},
    )
    return result.fetchone() is not None


def _invalid_identity_count() -> int:
    result = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM user_accounts "
            "WHERE (oidc_issuer IS NULL) <> (oidc_subject IS NULL) "
            "OR (oidc_issuer IS NOT NULL "
            "AND length(btrim(oidc_issuer, E' \\011\\012\\013\\014\\015')) = 0) "
            "OR (oidc_subject IS NOT NULL "
            "AND length(btrim(oidc_subject, E' \\011\\012\\013\\014\\015')) = 0)"
        )
    )
    return int(result.scalar_one())


def add_oidc_identity_constraint() -> None:
    if _constraint_exists():
        return  # Fresh installs receive the constraint from 001 metadata creation.

    invalid_count = _invalid_identity_count()
    if invalid_count:
        raise RuntimeError(
            "Cannot add OIDC identity-pair constraint: "
            f"{invalid_count} user account(s) have a partial or blank OIDC identity"
        )

    op.create_check_constraint(
        CONSTRAINT_NAME,
        "user_accounts",
        OIDC_IDENTITY_PAIR_EXPRESSION,
    )


def remove_oidc_identity_constraint() -> None:
    op.execute(
        sa.text(
            f"ALTER TABLE user_accounts DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"
        )
    )


def add_oidc_login_controls() -> None:
    op.add_column("oidc_auth_requests", sa.Column("source_fingerprint", sa.String(64)), if_not_exists=True)
    op.execute("""
        UPDATE oidc_auth_requests SET source_fingerprint = 'legacy-upgrade-020'
        WHERE source_fingerprint IS NULL
    """)
    op.execute("UPDATE oidc_auth_requests SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    op.alter_column("oidc_auth_requests", "source_fingerprint", nullable=False)
    op.alter_column("oidc_auth_requests", "created_at", nullable=False)
    op.create_index(
        "ix_oidc_auth_requests_source_created", "oidc_auth_requests",
        ["source_fingerprint", "created_at"], if_not_exists=True,
    )
    op.create_index("ix_oidc_auth_requests_created_at", "oidc_auth_requests", ["created_at"], if_not_exists=True)


def remove_oidc_login_controls() -> None:
    op.drop_index("ix_oidc_auth_requests_created_at", table_name="oidc_auth_requests")
    op.drop_column("oidc_auth_requests", "source_fingerprint")
    op.alter_column("oidc_auth_requests", "created_at", nullable=True)


def add_credential_cutoff() -> None:
    op.add_column(
        "user_accounts", sa.Column("credentials_invalidated_at", sa.DateTime(timezone=True)), if_not_exists=True,
    )


def remove_credential_cutoff() -> None:
    if not _has_column("user_accounts", "credentials_invalidated_at"):
        return

    bind = op.get_bind()
    # Lock before checking so a concurrent credential invalidation cannot land
    # between the check and the destructive ALTER TABLE.
    bind.execute(sa.text("LOCK TABLE user_accounts IN ACCESS EXCLUSIVE MODE"))
    has_active_cutoff = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM user_accounts "
            "WHERE credentials_invalidated_at IS NOT NULL"
            ")"
        )
    ).scalar_one()
    if has_active_cutoff:
        raise RuntimeError(
            "Cannot downgrade v0.6.0: "
            "user_accounts.credentials_invalidated_at contains non-NULL "
            "values. Dropping those cutoffs could resurrect invalidated local "
            "credentials after a later re-upgrade. Permanently remove the "
            "affected credentials before clearing the cutoffs and downgrading."
        )

    op.drop_column("user_accounts", "credentials_invalidated_at")


def add_passkey_controls() -> None:
    op.execute("""
        ALTER TABLE webauthn_challenges
        ADD COLUMN IF NOT EXISTS source_fingerprint VARCHAR(64),
        ADD COLUMN IF NOT EXISTS user_fingerprint VARCHAR(64)
    """)
    op.create_index(
        "ix_webauthn_challenges_source_created", "webauthn_challenges",
        ["source_fingerprint", "created_at"], if_not_exists=True,
    )
    op.create_index(
        "ix_webauthn_challenges_user_fingerprint_created", "webauthn_challenges",
        ["user_fingerprint", "created_at"], if_not_exists=True,
    )


def create_password_login_attempts() -> None:
    op.create_table(
        "password_login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_login_attempts_source_created",
        "password_login_attempts",
        ["source_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_password_login_attempts_created_at",
        "password_login_attempts",
        ["created_at"],
        unique=False,
    )


def create_api_key_failure_samples() -> None:
    op.create_table(
        "api_key_failure_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failure_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_key_failure_samples_source_created",
        "api_key_failure_samples",
        ["source_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_failure_samples_failure_created",
        "api_key_failure_samples",
        ["failure_fingerprint", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_api_key_failure_samples_created_at",
        "api_key_failure_samples",
        ["created_at"],
        unique=False,
    )


def create_password_work_tables() -> None:
    op.create_table(
        "password_hash_work_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_hash_work_leases_expires_at",
        "password_hash_work_leases",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "password_login_failure_counters",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_accounts.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "password_fingerprint"),
    )


def remove_password_work_tables() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE password_hash_work_leases, "
            "password_login_failure_counters IN ACCESS EXCLUSIVE MODE"
        )
    )
    active_leases = bind.execute(
        sa.text(
            "SELECT count(*) FROM password_hash_work_leases "
            "WHERE expires_at > CURRENT_TIMESTAMP"
        )
    ).scalar_one()
    pending_failures = bind.execute(
        sa.text("SELECT count(*) FROM password_login_failure_counters")
    ).scalar_one()
    if int(active_leases or 0) > 0 or int(pending_failures or 0) > 0:
        raise RuntimeError(
            "Refusing to downgrade password-work protections while active "
            "leases or pending failure counters exist"
        )

    op.drop_table("password_login_failure_counters")
    op.drop_table("password_hash_work_leases")


AUTH_SESSION_MAINTENANCE_JOBS = (
    {
        "name": "cleanup-expired-sessions",
        "schedule": "0 3 * * *",
        "command": "DELETE FROM auth_sessions WHERE expires_at < NOW() - INTERVAL '90 days';",
    },
    {
        "name": "vacuum-sessions-table",
        "schedule": "30 3 * * *",
        "command": "VACUUM ANALYZE auth_sessions;",
    },
)


def schedule_session_jobs() -> None:
    # Named scheduling is an idempotent upsert, so this replaces the stale
    # commands installed by the initial migration without a scheduling gap.
    for job in AUTH_SESSION_MAINTENANCE_JOBS:
        schedule_cron_job(**job)


def remove_session_jobs() -> None:
    # Do not restore commands that target the nonexistent `sessions` table.
    for job in AUTH_SESSION_MAINTENANCE_JOBS:
        unschedule_cron_job(name=job["name"])
