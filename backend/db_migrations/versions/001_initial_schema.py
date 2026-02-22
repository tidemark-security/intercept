"""Initial schema for Tidemark Intercept

Revision ID: 001_initial
Revises: None
Create Date: 2026-02-01

Consolidated migration that creates the complete schema:

1. Tables via SQLModel.metadata.create_all()
2. Custom PostgreSQL enums (accounttype, recommendationstatus, triagedisposition, rejectioncategory, messagefeedback)
3. Partial unique index for human user emails
4. Full-text search infrastructure:
   - search_vector columns on alerts/cases/tasks
   - extract_timeline_text() function with nested reply support
   - Trigger functions for search_vector updates
   - GIN indexes on search_vector columns
   - GIN indexes on timeline_items JSONB columns
5. Trigram indexes for fuzzy search on title/description
6. Materialized views (soc_metrics_15m, analyst_metrics_15m, alert_metrics_15m)

Prerequisites (handled by init.sql before Alembic runs):
- Extensions: uuid-ossp, pg_trgm, vector

Note: pg_cron scheduled jobs are managed by migration 002_pgcron_jobs.py
which opens a separate connection to the postgres database.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

# Import all models to register them with SQLModel metadata
from app.models import models  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # STEP 1: Create custom PostgreSQL enums BEFORE tables
    # These must exist before SQLModel creates columns that reference them
    # =========================================================================
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE accounttype AS ENUM ('HUMAN', 'NHI');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE recommendationstatus AS ENUM ('QUEUED', 'PENDING', 'ACCEPTED', 'REJECTED', 'SUPERSEDED', 'FAILED');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE triagedisposition AS ENUM ('TRUE_POSITIVE', 'FALSE_POSITIVE', 'BENIGN', 'NEEDS_INVESTIGATION', 'DUPLICATE', 'UNKNOWN');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE rejectioncategory AS ENUM (
                'INCORRECT_DISPOSITION',
                'WRONG_SUGGESTED_STATUS',
                'WRONG_PRIORITY',
                'MISSING_CONTEXT',
                'INCOMPLETE_ANALYSIS',
                'PREFER_MANUAL_REVIEW',
                'FALSE_REASONING',
                'OTHER',
                'SUPERSEDED_MANUAL_TRIAGE'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagefeedback AS ENUM ('POSITIVE', 'NEGATIVE');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    # =========================================================================
    # STEP 2: Create all tables via SQLModel
    # This is equivalent to SQLModel.metadata.create_all(engine)
    # =========================================================================
    
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)
    
    # =========================================================================
    # STEP 3: Create partial unique index for human user emails
    # Ensures email uniqueness only for HUMAN accounts (NHI accounts can share emails)
    # =========================================================================
    
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_user_accounts_email_human 
        ON user_accounts (email) 
        WHERE account_type = 'HUMAN';
    """)
    
    # =========================================================================
    # STEP 4: Add search_vector columns to alerts/cases/tasks
    # These tsvector columns are populated by triggers for full-text search
    # =========================================================================
    
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS search_vector tsvector;")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS search_vector tsvector;")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS search_vector tsvector;")
    
    # =========================================================================
    # STEP 5: Create extract_timeline_text function with nested reply support
    # Used by search vector triggers to extract searchable text from timeline JSONB
    # =========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION extract_timeline_text(items JSONB)
        RETURNS TEXT AS $$
        WITH RECURSIVE all_items AS (
            -- Base case: top-level timeline items
            SELECT item
            FROM jsonb_array_elements(COALESCE(items, '[]'::jsonb)) AS item
            
            UNION ALL
            
            -- Recursive case: nested replies within items
            SELECT reply
            FROM all_items,
                 jsonb_array_elements(COALESCE(all_items.item->'replies', '[]'::jsonb)) AS reply
            WHERE all_items.item->'replies' IS NOT NULL
              AND jsonb_typeof(all_items.item->'replies') = 'array'
        )
        SELECT COALESCE(
            string_agg(
                -- Base/common fields
                COALESCE(item->>'description', '') || ' ' ||
                COALESCE(item->>'name', '') || ' ' ||
                
                -- Observable (IOC value - CRITICAL for security search)
                COALESCE(item->>'observable_value', '') || ' ' ||
                
                -- TTP/MITRE ATT&CK fields
                COALESCE(item->>'mitre_id', '') || ' ' ||
                COALESCE(item->>'title', '') || ' ' ||
                COALESCE(item->>'tactic', '') || ' ' ||
                COALESCE(item->>'technique', '') || ' ' ||
                COALESCE(item->>'mitre_description', '') || ' ' ||
                
                -- System fields
                COALESCE(item->>'hostname', '') || ' ' ||
                COALESCE(item->>'ip_address', '') || ' ' ||
                COALESCE(item->>'cmdb_id', '') || ' ' ||
                
                -- Process execution fields (malware/threat hunting)
                COALESCE(item->>'process_name', '') || ' ' ||
                COALESCE(item->>'command_line', '') || ' ' ||
                COALESCE(item->>'user_account', '') || ' ' ||
                
                -- Registry change fields (persistence hunting)
                COALESCE(item->>'registry_key', '') || ' ' ||
                COALESCE(item->>'registry_value', '') || ' ' ||
                COALESCE(item->>'old_data', '') || ' ' ||
                COALESCE(item->>'new_data', '') || ' ' ||
                
                -- Network traffic fields (lateral movement, C2)
                COALESCE(item->>'source_ip', '') || ' ' ||
                COALESCE(item->>'destination_ip', '') || ' ' ||
                
                -- Email fields (phishing investigation)
                COALESCE(item->>'sender', '') || ' ' ||
                COALESCE(item->>'recipient', '') || ' ' ||
                COALESCE(item->>'subject', '') || ' ' ||
                
                -- Attachment/Link/Artifact fields
                COALESCE(item->>'file_name', '') || ' ' ||
                COALESCE(item->>'url', '') || ' ' ||
                COALESCE(item->>'hash', '') || ' ' ||
                
                -- Actor fields (people involved)
                COALESCE(item->>'user_id', '') || ' ' ||
                COALESCE(item->>'org', '') || ' ' ||
                COALESCE(item->>'contact_email', '') || ' ' ||
                COALESCE(item->>'tag_id', '') || ' ' ||
                
                -- Linked entity metadata
                COALESCE(item->>'assignee', '') || ' ' ||
                COALESCE(item->>'task_human_id', '') || ' ' ||
                
                -- Tags array (convert to space-separated string)
                COALESCE(
                    (SELECT string_agg(tag, ' ')
                     FROM jsonb_array_elements_text(
                         CASE WHEN jsonb_typeof(item->'tags') = 'array' 
                              THEN item->'tags' 
                              ELSE '[]'::jsonb 
                         END
                     ) AS tag),
                    ''
                ) || ' ' ||
                
                -- Recipients array for emails (convert to space-separated string)
                COALESCE(
                    (SELECT string_agg(r, ' ')
                     FROM jsonb_array_elements_text(
                         CASE WHEN jsonb_typeof(item->'recipients') = 'array' 
                              THEN item->'recipients' 
                              ELSE '[]'::jsonb 
                         END
                     ) AS r),
                    ''
                ),
                ' '
            ),
            ''
        )
        FROM all_items
        $$ LANGUAGE SQL IMMUTABLE;
    """)
    
    # =========================================================================
    # STEP 6: Create trigger functions for search vector updates
    # Each table gets weighted zones: A=title, B=description, C=source/assignee, D=timeline
    # =========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION update_alert_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.source, '')), 'C') ||
                setweight(to_tsvector('english', extract_timeline_text(NEW.timeline_items)), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE OR REPLACE FUNCTION update_case_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.assignee, '')), 'C') ||
                setweight(to_tsvector('english', extract_timeline_text(NEW.timeline_items)), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE OR REPLACE FUNCTION update_task_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.assignee, '')), 'C') ||
                setweight(to_tsvector('english', extract_timeline_text(NEW.timeline_items)), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # =========================================================================
    # STEP 7: Create triggers on alerts/cases/tasks tables
    # =========================================================================
    
    op.execute("""
        DROP TRIGGER IF EXISTS trg_alerts_search_vector ON alerts;
        CREATE TRIGGER trg_alerts_search_vector
        BEFORE INSERT OR UPDATE ON alerts
        FOR EACH ROW EXECUTE FUNCTION update_alert_search_vector();
    """)
    
    op.execute("""
        DROP TRIGGER IF EXISTS trg_cases_search_vector ON cases;
        CREATE TRIGGER trg_cases_search_vector
        BEFORE INSERT OR UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION update_case_search_vector();
    """)
    
    op.execute("""
        DROP TRIGGER IF EXISTS trg_tasks_search_vector ON tasks;
        CREATE TRIGGER trg_tasks_search_vector
        BEFORE INSERT OR UPDATE ON tasks
        FOR EACH ROW EXECUTE FUNCTION update_task_search_vector();
    """)
    
    # =========================================================================
    # STEP 8: Create GIN indexes for full-text search
    # =========================================================================
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_search_vector ON alerts USING gin(search_vector);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cases_search_vector ON cases USING gin(search_vector);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_search_vector ON tasks USING gin(search_vector);")
    
    # =========================================================================
    # STEP 9: Create GIN indexes on timeline_items JSONB for containment queries
    # =========================================================================
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timeline_gin ON alerts USING gin(timeline_items jsonb_path_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cases_timeline_gin ON cases USING gin(timeline_items jsonb_path_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_timeline_gin ON tasks USING gin(timeline_items jsonb_path_ops);")
    
    # =========================================================================
    # STEP 10: Create GIN trigram indexes for fuzzy search
    # Accelerates similarity() function calls and ILIKE queries
    # =========================================================================
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_title_trgm ON alerts USING gin(title gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_description_trgm ON alerts USING gin(description gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cases_title_trgm ON cases USING gin(title gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cases_description_trgm ON cases USING gin(description gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm ON tasks USING gin(title gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_description_trgm ON tasks USING gin(description gin_trgm_ops);")
    
    # =========================================================================
    # STEP 11: Create SOC metrics materialized views
    # =========================================================================
    
    # SOC Metrics View - 15 minute windows with alert/case/task aggregations
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS soc_metrics_15m AS
        WITH alert_metrics AS (
            SELECT
                date_trunc('hour', created_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
                priority,
                source,
                COUNT(*) AS alert_count,
                COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS alerts_closed,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS alerts_tp,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS alerts_fp,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS alerts_bp,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS alerts_duplicate,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_UNRESOLVED') AS alerts_unresolved,
                COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS alerts_escalated,
                COUNT(*) FILTER (WHERE status::text IN ('IN_PROGRESS', 'ESCALATED') OR status::text LIKE 'CLOSED_%') AS alerts_triaged,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
                ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p50_seconds,
                AVG(EXTRACT(EPOCH FROM (triaged_at - created_at))) 
                    FILTER (WHERE triaged_at IS NOT NULL) AS mttt_mean_seconds,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
                ) FILTER (WHERE triaged_at IS NOT NULL) AS mttt_p95_seconds
            FROM alerts
            WHERE created_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2, 3
        ),
        case_metrics AS (
            SELECT
                date_trunc('hour', created_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
                priority,
                COUNT(*) AS case_count,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED') AS cases_closed,
                COUNT(*) FILTER (WHERE status::text = 'NEW') AS cases_new,
                COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS cases_in_progress,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
                ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p50_seconds,
                AVG(EXTRACT(EPOCH FROM (closed_at - created_at))) 
                    FILTER (WHERE closed_at IS NOT NULL) AS mttr_mean_seconds,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (closed_at - created_at))
                ) FILTER (WHERE closed_at IS NOT NULL) AS mttr_p95_seconds
            FROM cases
            WHERE created_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2
        ),
        task_metrics AS (
            SELECT
                date_trunc('hour', created_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
                priority,
                COUNT(*) AS task_count,
                COUNT(*) FILTER (WHERE status::text = 'DONE') AS tasks_completed,
                COUNT(*) FILTER (WHERE status::text = 'TODO') AS tasks_todo,
                COUNT(*) FILTER (WHERE status::text = 'IN_PROGRESS') AS tasks_in_progress
            FROM tasks
            WHERE created_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2
        )
        SELECT
            COALESCE(a.time_window, c.time_window, t.time_window) AS time_window,
            COALESCE(a.priority, c.priority, t.priority) AS priority,
            a.source AS alert_source,
            COALESCE(a.alert_count, 0) AS alert_count,
            COALESCE(a.alerts_closed, 0) AS alerts_closed,
            COALESCE(a.alerts_tp, 0) AS alerts_tp,
            COALESCE(a.alerts_fp, 0) AS alerts_fp,
            COALESCE(a.alerts_bp, 0) AS alerts_bp,
            COALESCE(a.alerts_duplicate, 0) AS alerts_duplicate,
            COALESCE(a.alerts_unresolved, 0) AS alerts_unresolved,
            COALESCE(a.alerts_escalated, 0) AS alerts_escalated,
            COALESCE(a.alerts_triaged, 0) AS alerts_triaged,
            a.mttt_p50_seconds,
            a.mttt_mean_seconds,
            a.mttt_p95_seconds,
            COALESCE(c.case_count, 0) AS case_count,
            COALESCE(c.cases_closed, 0) AS cases_closed,
            COALESCE(c.cases_new, 0) AS cases_new,
            COALESCE(c.cases_in_progress, 0) AS cases_in_progress,
            c.mttr_p50_seconds,
            c.mttr_mean_seconds,
            c.mttr_p95_seconds,
            COALESCE(t.task_count, 0) AS task_count,
            COALESCE(t.tasks_completed, 0) AS tasks_completed,
            COALESCE(t.tasks_todo, 0) AS tasks_todo,
            COALESCE(t.tasks_in_progress, 0) AS tasks_in_progress,
            NOW() AS refreshed_at
        FROM alert_metrics a
        FULL OUTER JOIN case_metrics c ON a.time_window = c.time_window AND a.priority::text = c.priority::text
        FULL OUTER JOIN task_metrics t ON COALESCE(a.time_window, c.time_window) = t.time_window 
            AND COALESCE(a.priority::text, c.priority::text) = t.priority::text
        WHERE COALESCE(a.time_window, c.time_window, t.time_window) IS NOT NULL;
    """)
    
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS soc_metrics_15m_idx 
        ON soc_metrics_15m (time_window, priority, alert_source);
    """)
    
    # Analyst Metrics View - 15 minute windows with per-analyst aggregations
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS analyst_metrics_15m AS
        WITH alert_triage AS (
            SELECT
                date_trunc('hour', triaged_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM triaged_at) / 15) AS time_window,
                assignee AS analyst,
                COUNT(*) AS alerts_triaged,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS alerts_tp,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS alerts_fp,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS alerts_bp,
                COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS alerts_escalated,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS alerts_duplicate,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (triaged_at - created_at))
                ) AS mttt_p50_seconds,
                AVG(EXTRACT(EPOCH FROM (triaged_at - created_at))) AS mttt_mean_seconds
            FROM alerts
            WHERE triaged_at IS NOT NULL
              AND assignee IS NOT NULL
              AND triaged_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2
        ),
        case_participation AS (
            SELECT
                date_trunc('hour', updated_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM updated_at) / 15) AS time_window,
                assignee AS analyst,
                COUNT(DISTINCT id) AS cases_assigned,
                COUNT(*) FILTER (WHERE status::text = 'CLOSED') AS cases_closed
            FROM cases
            WHERE assignee IS NOT NULL
              AND updated_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2
        ),
        task_completion AS (
            SELECT
                date_trunc('hour', updated_at) + 
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM updated_at) / 15) AS time_window,
                assignee AS analyst,
                COUNT(*) AS tasks_assigned,
                COUNT(*) FILTER (WHERE status::text = 'DONE') AS tasks_completed
            FROM tasks
            WHERE assignee IS NOT NULL
              AND updated_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2
        )
        SELECT
            COALESCE(a.time_window, c.time_window, t.time_window) AS time_window,
            COALESCE(a.analyst, c.analyst, t.analyst) AS analyst,
            COALESCE(a.alerts_triaged, 0) AS alerts_triaged,
            COALESCE(a.alerts_tp, 0) AS alerts_tp,
            COALESCE(a.alerts_fp, 0) AS alerts_fp,
            COALESCE(a.alerts_bp, 0) AS alerts_bp,
            COALESCE(a.alerts_escalated, 0) AS alerts_escalated,
            COALESCE(a.alerts_duplicate, 0) AS alerts_duplicate,
            a.mttt_p50_seconds,
            a.mttt_mean_seconds,
            COALESCE(c.cases_assigned, 0) AS cases_assigned,
            COALESCE(c.cases_closed, 0) AS cases_closed,
            COALESCE(t.tasks_assigned, 0) AS tasks_assigned,
            COALESCE(t.tasks_completed, 0) AS tasks_completed,
            NOW() AS refreshed_at
        FROM alert_triage a
        FULL OUTER JOIN case_participation c ON a.time_window = c.time_window AND a.analyst = c.analyst
        FULL OUTER JOIN task_completion t ON COALESCE(a.time_window, c.time_window) = t.time_window 
            AND COALESCE(a.analyst, c.analyst) = t.analyst
        WHERE COALESCE(a.time_window, c.time_window, t.time_window) IS NOT NULL
          AND COALESCE(a.analyst, c.analyst, t.analyst) IS NOT NULL;
    """)
    
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS analyst_metrics_15m_idx 
        ON analyst_metrics_15m (time_window, analyst);
    """)
    
    # Alert Metrics View - 15 minute windows with detection engineering focus
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS alert_metrics_15m AS
        SELECT
            date_trunc('hour', created_at) + 
                INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM created_at) / 15) AS time_window,
            source,
            priority,
            EXTRACT(HOUR FROM created_at) AS hour_of_day,
            EXTRACT(DOW FROM created_at) AS day_of_week,
            COUNT(*) AS alert_count,
            COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') AS alerts_closed,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_TP') AS alerts_tp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP') AS alerts_fp,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_BP') AS alerts_bp,
            COUNT(*) FILTER (WHERE status::text = 'ESCALATED') AS alerts_escalated,
            COUNT(*) FILTER (WHERE status::text = 'CLOSED_DUPLICATE') AS alerts_duplicate,
            CASE 
                WHEN COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%') > 0 
                THEN COUNT(*) FILTER (WHERE status::text = 'CLOSED_FP')::float / 
                     COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%')
                ELSE NULL 
            END AS fp_rate,
            CASE 
                WHEN COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%' OR status::text = 'ESCALATED') > 0 
                THEN COUNT(*) FILTER (WHERE status::text = 'ESCALATED')::float / 
                     COUNT(*) FILTER (WHERE status::text LIKE 'CLOSED_%' OR status::text = 'ESCALATED')
                ELSE NULL 
            END AS escalation_rate,
            NOW() AS refreshed_at
        FROM alerts
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1, 2, 3, 4, 5;
    """)
    
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS alert_metrics_15m_idx 
        ON alert_metrics_15m (time_window, source, priority, hour_of_day, day_of_week);
    """)
    


def downgrade() -> None:
    # Drop materialized views
    op.execute("DROP MATERIALIZED VIEW IF EXISTS alert_metrics_15m CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analyst_metrics_15m CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS soc_metrics_15m CASCADE;")
    
    # Drop trigram indexes
    op.execute("DROP INDEX IF EXISTS idx_tasks_description_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_tasks_title_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_cases_description_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_cases_title_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_alerts_description_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_alerts_title_trgm;")
    
    # Drop JSONB GIN indexes
    op.execute("DROP INDEX IF EXISTS idx_tasks_timeline_gin;")
    op.execute("DROP INDEX IF EXISTS idx_cases_timeline_gin;")
    op.execute("DROP INDEX IF EXISTS idx_alerts_timeline_gin;")
    
    # Drop search vector GIN indexes
    op.execute("DROP INDEX IF EXISTS idx_tasks_search_vector;")
    op.execute("DROP INDEX IF EXISTS idx_cases_search_vector;")
    op.execute("DROP INDEX IF EXISTS idx_alerts_search_vector;")
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_search_vector ON tasks;")
    op.execute("DROP TRIGGER IF EXISTS trg_cases_search_vector ON cases;")
    op.execute("DROP TRIGGER IF EXISTS trg_alerts_search_vector ON alerts;")
    
    # Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS update_task_search_vector();")
    op.execute("DROP FUNCTION IF EXISTS update_case_search_vector();")
    op.execute("DROP FUNCTION IF EXISTS update_alert_search_vector();")
    op.execute("DROP FUNCTION IF EXISTS extract_timeline_text(JSONB);")
    
    # Drop search_vector columns
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS search_vector;")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS search_vector;")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS search_vector;")
    
    # Drop partial unique index
    op.execute("DROP INDEX IF EXISTS ix_user_accounts_email_human;")
    
    # Drop all tables
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind)
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS messagefeedback;")
    op.execute("DROP TYPE IF EXISTS rejectioncategory;")
    op.execute("DROP TYPE IF EXISTS triagedisposition;")
    op.execute("DROP TYPE IF EXISTS recommendationstatus;")
    op.execute("DROP TYPE IF EXISTS accounttype;")
