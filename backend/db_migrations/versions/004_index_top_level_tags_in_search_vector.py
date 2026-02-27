"""Include top-level entity tags in search vectors

Revision ID: 004_tags_in_search_vector
Revises: 003_passkey_support
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "004_tags_in_search_vector"
down_revision: Union[str, None] = "003_passkey_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION update_alert_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.source, '')), 'C') ||
                setweight(
                    to_tsvector(
                        'english',
                        COALESCE(
                            (
                                SELECT string_agg(tag, ' ')
                                FROM jsonb_array_elements_text(
                                    CASE
                                        WHEN jsonb_typeof(NEW.tags) = 'array' THEN NEW.tags
                                        ELSE '[]'::jsonb
                                    END
                                ) AS tag
                            ),
                            ''
                        )
                    ),
                    'B'
                ) ||
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
                setweight(
                    to_tsvector(
                        'english',
                        COALESCE(
                            (
                                SELECT string_agg(tag, ' ')
                                FROM jsonb_array_elements_text(
                                    CASE
                                        WHEN jsonb_typeof(NEW.tags) = 'array' THEN NEW.tags
                                        ELSE '[]'::jsonb
                                    END
                                ) AS tag
                            ),
                            ''
                        )
                    ),
                    'B'
                ) ||
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
                setweight(
                    to_tsvector(
                        'english',
                        COALESCE(
                            (
                                SELECT string_agg(tag, ' ')
                                FROM jsonb_array_elements_text(
                                    CASE
                                        WHEN jsonb_typeof(NEW.tags) = 'array' THEN NEW.tags
                                        ELSE '[]'::jsonb
                                    END
                                ) AS tag
                            ),
                            ''
                        )
                    ),
                    'B'
                ) ||
                setweight(to_tsvector('english', extract_timeline_text(NEW.timeline_items)), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("UPDATE alerts SET updated_at = updated_at;")
    op.execute("UPDATE cases SET updated_at = updated_at;")
    op.execute("UPDATE tasks SET updated_at = updated_at;")


def downgrade() -> None:
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

    op.execute("UPDATE alerts SET updated_at = updated_at;")
    op.execute("UPDATE cases SET updated_at = updated_at;")
    op.execute("UPDATE tasks SET updated_at = updated_at;")
