"""Create unified audit_logs table and schedule audit retention jobs.

Revision ID: 007_unified_audit_logs
Revises: 006_enrichment_framework
Create Date: 2026-03-15
"""

from typing import Sequence, Union

from alembic import op

from db_migrations.cron_utils import schedule_cron_job, unschedule_cron_job


revision: str = "007_unified_audit_logs"
down_revision: Union[str, None] = "006_enrichment_framework"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RETENTION_JOBS = [
    {
        "name": "audit-retention-auth",
        "schedule": "0 2 * * *",
        "command": (
            "DELETE FROM audit_logs "
            "WHERE event_type LIKE 'auth.%' "
            "AND performed_at < NOW() - INTERVAL '90 days';"
        ),
    },
    {
        "name": "audit-retention-settings",
        "schedule": "5 2 * * *",
        "command": (
            "DELETE FROM audit_logs "
            "WHERE event_type LIKE 'settings.%' "
            "AND performed_at < NOW() - INTERVAL '180 days';"
        ),
    },
    {
        "name": "vacuum-audit-logs",
        "schedule": "15 2 * * *",
        "command": "VACUUM ANALYZE audit_logs;",
    },
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(200) NOT NULL,
            entity_type VARCHAR(100),
            entity_id VARCHAR(255),
            item_id VARCHAR(255),
            description TEXT,
            old_value TEXT,
            new_value TEXT,
            performed_by VARCHAR(100),
            performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(100),
            user_agent TEXT,
            correlation_id VARCHAR(255)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_lookup ON audit_logs (entity_type, entity_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs (event_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_performed_at ON audit_logs (performed_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_performed_by ON audit_logs (performed_by);"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_timeline_coalesce
        ON audit_logs (entity_type, entity_id)
        WHERE event_type IN ('timeline.item.updated', 'timeline.item.deleted')
          AND item_id IS NOT NULL;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'case_audit_logs'
            ) THEN
                INSERT INTO audit_logs (
                    event_type,
                    entity_type,
                    entity_id,
                    description,
                    old_value,
                    new_value,
                    performed_by,
                    performed_at
                )
                SELECT
                    CASE
                        WHEN action = 'created' THEN 'case.created'
                        WHEN action = 'deleted' THEN 'case.deleted'
                        WHEN action = 'linked_items_closed' THEN 'case.linked_items_closed'
                        WHEN action = 'timeline_item_added' THEN 'timeline.item.added'
                        WHEN action = 'timeline_item_updated' THEN 'timeline.item.updated'
                        WHEN action = 'timeline_item_deleted' THEN 'timeline.item.deleted'
                        WHEN action LIKE '%_changed' THEN 'case.' || action
                        ELSE 'case.' || action
                    END AS event_type,
                    'case' AS entity_type,
                    case_id::text AS entity_id,
                    description,
                    old_value,
                    new_value,
                    performed_by,
                    performed_at
                FROM case_audit_logs;
            END IF;
        END $$;
        """
    )

    op.execute("DROP TABLE IF EXISTS case_audit_logs;")

    for job in RETENTION_JOBS:
        schedule_cron_job(
            name=job["name"],
            schedule=job["schedule"],
            command=job["command"],
        )


def downgrade() -> None:
    for job in RETENTION_JOBS:
        unschedule_cron_job(job["name"])

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS case_audit_logs (
            id SERIAL PRIMARY KEY,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            action VARCHAR(100) NOT NULL,
            description TEXT,
            old_value TEXT,
            new_value TEXT,
            performed_by VARCHAR(100) NOT NULL,
            performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        INSERT INTO case_audit_logs (
            case_id,
            action,
            description,
            old_value,
            new_value,
            performed_by,
            performed_at
        )
        SELECT
            entity_id::integer,
            CASE
                WHEN event_type = 'case.created' THEN 'created'
                WHEN event_type = 'case.deleted' THEN 'deleted'
                WHEN event_type = 'case.linked_items_closed' THEN 'linked_items_closed'
                WHEN event_type = 'timeline.item.added' THEN 'timeline_item_added'
                WHEN event_type = 'timeline.item.updated' THEN 'timeline_item_updated'
                WHEN event_type = 'timeline.item.deleted' THEN 'timeline_item_deleted'
                WHEN event_type LIKE 'case.%' THEN replace(event_type, 'case.', '')
                ELSE event_type
            END,
            description,
            old_value,
            new_value,
            COALESCE(performed_by, 'system'),
            performed_at
        FROM audit_logs
        WHERE entity_type = 'case' AND entity_id IS NOT NULL;
        """
    )
    op.execute("DROP TABLE IF EXISTS audit_logs;")