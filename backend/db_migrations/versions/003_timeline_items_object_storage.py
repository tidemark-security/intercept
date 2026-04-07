"""Convert timeline_items storage from arrays to objects.

Revision ID: 003_timeline_obj_store
Revises: 002_oidc_browser_binding_hash
Create Date: 2026-04-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "003_timeline_obj_store"
down_revision: Union[str, None] = "002_oidc_browser_binding_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_items_to_object(items JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN items IS NULL THEN '{}'::jsonb
            WHEN jsonb_typeof(items) = 'array' THEN COALESCE(
                (
                    SELECT jsonb_object_agg(item->>'id', item)
                    FROM jsonb_array_elements(items) AS item
                ),
                '{}'::jsonb
            )
            WHEN jsonb_typeof(items) = 'object' THEN COALESCE(
                (
                    SELECT jsonb_object_agg(key, value)
                    FROM jsonb_each(items)
                ),
                '{}'::jsonb
            )
            ELSE '{}'::jsonb
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_item_normalize(item JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN item IS NULL OR jsonb_typeof(item) <> 'object' THEN item
            ELSE jsonb_set(
                item,
                '{replies}',
                timeline_items_to_object(COALESCE(item->'replies', '[]'::jsonb)),
                true
            )
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_items_to_object(items JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN items IS NULL THEN '{}'::jsonb
            WHEN jsonb_typeof(items) = 'array' THEN COALESCE(
                (
                    SELECT jsonb_object_agg(item->>'id', timeline_item_normalize(item))
                    FROM jsonb_array_elements(items) AS item
                ),
                '{}'::jsonb
            )
            WHEN jsonb_typeof(items) = 'object' THEN COALESCE(
                (
                    SELECT jsonb_object_agg(key, timeline_item_normalize(value))
                    FROM jsonb_each(items)
                ),
                '{}'::jsonb
            )
            ELSE '{}'::jsonb
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        UPDATE alerts
        SET timeline_items = timeline_items_to_object(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        UPDATE cases
        SET timeline_items = timeline_items_to_object(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        UPDATE tasks
        SET timeline_items = timeline_items_to_object(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION extract_timeline_text(items JSONB)
        RETURNS TEXT AS $$
        WITH RECURSIVE all_items AS (
            SELECT item
            FROM (
                SELECT value AS item
                FROM jsonb_each(
                    CASE
                        WHEN jsonb_typeof(items) = 'object' THEN items
                        ELSE '{}'::jsonb
                    END
                )
                UNION ALL
                SELECT value AS item
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(items) = 'array' THEN items
                        ELSE '[]'::jsonb
                    END
                )
            ) timeline_root_items

            UNION ALL

            SELECT reply
            FROM all_items,
                LATERAL (
                    SELECT value AS reply
                    FROM jsonb_each(
                        CASE
                            WHEN jsonb_typeof(all_items.item->'replies') = 'object' THEN all_items.item->'replies'
                            ELSE '{}'::jsonb
                        END
                    )
                    UNION ALL
                    SELECT value AS reply
                    FROM jsonb_array_elements(
                        CASE
                            WHEN jsonb_typeof(all_items.item->'replies') = 'array' THEN all_items.item->'replies'
                            ELSE '[]'::jsonb
                        END
                    )
                ) reply_items
        )
        SELECT COALESCE(
            string_agg(
                COALESCE(item->>'description', '') || ' ' ||
                COALESCE(item->>'name', '') || ' ' ||
                COALESCE(item->>'observable_value', '') || ' ' ||
                COALESCE(item->>'mitre_id', '') || ' ' ||
                COALESCE(item->>'title', '') || ' ' ||
                COALESCE(item->>'tactic', '') || ' ' ||
                COALESCE(item->>'technique', '') || ' ' ||
                COALESCE(item->>'mitre_description', '') || ' ' ||
                COALESCE(item->>'hostname', '') || ' ' ||
                COALESCE(item->>'ip_address', '') || ' ' ||
                COALESCE(item->>'cmdb_id', '') || ' ' ||
                COALESCE(item->>'process_name', '') || ' ' ||
                COALESCE(item->>'command_line', '') || ' ' ||
                COALESCE(item->>'user_account', '') || ' ' ||
                COALESCE(item->>'registry_key', '') || ' ' ||
                COALESCE(item->>'registry_value', '') || ' ' ||
                COALESCE(item->>'old_data', '') || ' ' ||
                COALESCE(item->>'new_data', '') || ' ' ||
                COALESCE(item->>'source_ip', '') || ' ' ||
                COALESCE(item->>'destination_ip', '') || ' ' ||
                COALESCE(item->>'sender', '') || ' ' ||
                COALESCE(item->>'recipient', '') || ' ' ||
                COALESCE(item->>'subject', '') || ' ' ||
                COALESCE(item->>'file_name', '') || ' ' ||
                COALESCE(item->>'url', '') || ' ' ||
                COALESCE(item->>'hash', '') || ' ' ||
                COALESCE(item->>'user_id', '') || ' ' ||
                COALESCE(item->>'org', '') || ' ' ||
                COALESCE(item->>'contact_email', '') || ' ' ||
                COALESCE(item->>'tag_id', '') || ' ' ||
                COALESCE(item->>'assignee', '') || ' ' ||
                COALESCE(item->>'task_human_id', '') || ' ' ||
                COALESCE(
                    (
                        SELECT string_agg(tag, ' ')
                        FROM jsonb_array_elements_text(
                            CASE
                                WHEN jsonb_typeof(item->'tags') = 'array' THEN item->'tags'
                                ELSE '[]'::jsonb
                            END
                        ) AS tag
                    ),
                    ''
                ) || ' ' ||
                COALESCE(
                    (
                        SELECT string_agg(r, ' ')
                        FROM jsonb_array_elements_text(
                            CASE
                                WHEN jsonb_typeof(item->'recipients') = 'array' THEN item->'recipients'
                                ELSE '[]'::jsonb
                            END
                        ) AS r
                    ),
                    ''
                ),
                ' '
            ),
            ''
        )
        FROM all_items
        $$ LANGUAGE SQL IMMUTABLE;
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_items_to_array(items JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN items IS NULL THEN '[]'::jsonb
            WHEN jsonb_typeof(items) = 'array' THEN items
            WHEN jsonb_typeof(items) = 'object' THEN COALESCE(
                (
                    SELECT jsonb_agg(value)
                    FROM jsonb_each(items)
                ),
                '[]'::jsonb
            )
            ELSE '[]'::jsonb
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_item_denormalize(item JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN item IS NULL OR jsonb_typeof(item) <> 'object' THEN item
            ELSE jsonb_set(
                item,
                '{replies}',
                timeline_items_to_array(COALESCE(item->'replies', '{}'::jsonb)),
                true
            )
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION timeline_items_to_array(items JSONB)
        RETURNS JSONB AS $$
        SELECT CASE
            WHEN items IS NULL THEN '[]'::jsonb
            WHEN jsonb_typeof(items) = 'array' THEN items
            WHEN jsonb_typeof(items) = 'object' THEN COALESCE(
                (
                    SELECT jsonb_agg(timeline_item_denormalize(value))
                    FROM jsonb_each(items)
                ),
                '[]'::jsonb
            )
            ELSE '[]'::jsonb
        END
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("""
        UPDATE alerts
        SET timeline_items = timeline_items_to_array(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        UPDATE cases
        SET timeline_items = timeline_items_to_array(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        UPDATE tasks
        SET timeline_items = timeline_items_to_array(timeline_items)
        WHERE timeline_items IS NOT NULL;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION extract_timeline_text(items JSONB)
        RETURNS TEXT AS $$
        WITH RECURSIVE all_items AS (
            SELECT item
            FROM jsonb_array_elements(COALESCE(items, '[]'::jsonb)) AS item

            UNION ALL

            SELECT reply
            FROM all_items,
                 jsonb_array_elements(COALESCE(all_items.item->'replies', '[]'::jsonb)) AS reply
            WHERE all_items.item->'replies' IS NOT NULL
              AND jsonb_typeof(all_items.item->'replies') = 'array'
        )
        SELECT COALESCE(
            string_agg(
                COALESCE(item->>'description', '') || ' ' ||
                COALESCE(item->>'name', '') || ' ' ||
                COALESCE(item->>'observable_value', '') || ' ' ||
                COALESCE(item->>'mitre_id', '') || ' ' ||
                COALESCE(item->>'title', '') || ' ' ||
                COALESCE(item->>'tactic', '') || ' ' ||
                COALESCE(item->>'technique', '') || ' ' ||
                COALESCE(item->>'mitre_description', '') || ' ' ||
                COALESCE(item->>'hostname', '') || ' ' ||
                COALESCE(item->>'ip_address', '') || ' ' ||
                COALESCE(item->>'cmdb_id', '') || ' ' ||
                COALESCE(item->>'process_name', '') || ' ' ||
                COALESCE(item->>'command_line', '') || ' ' ||
                COALESCE(item->>'user_account', '') || ' ' ||
                COALESCE(item->>'registry_key', '') || ' ' ||
                COALESCE(item->>'registry_value', '') || ' ' ||
                COALESCE(item->>'old_data', '') || ' ' ||
                COALESCE(item->>'new_data', '') || ' ' ||
                COALESCE(item->>'source_ip', '') || ' ' ||
                COALESCE(item->>'destination_ip', '') || ' ' ||
                COALESCE(item->>'sender', '') || ' ' ||
                COALESCE(item->>'recipient', '') || ' ' ||
                COALESCE(item->>'subject', '') || ' ' ||
                COALESCE(item->>'file_name', '') || ' ' ||
                COALESCE(item->>'url', '') || ' ' ||
                COALESCE(item->>'hash', '') || ' ' ||
                COALESCE(item->>'user_id', '') || ' ' ||
                COALESCE(item->>'org', '') || ' ' ||
                COALESCE(item->>'contact_email', '') || ' ' ||
                COALESCE(item->>'tag_id', '') || ' ' ||
                COALESCE(item->>'assignee', '') || ' ' ||
                COALESCE(item->>'task_human_id', '') || ' ' ||
                COALESCE(
                    (
                        SELECT string_agg(tag, ' ')
                        FROM jsonb_array_elements_text(
                            CASE WHEN jsonb_typeof(item->'tags') = 'array'
                                 THEN item->'tags'
                                 ELSE '[]'::jsonb
                            END
                        ) AS tag
                    ),
                    ''
                ) || ' ' ||
                COALESCE(
                    (
                        SELECT string_agg(r, ' ')
                        FROM jsonb_array_elements_text(
                            CASE WHEN jsonb_typeof(item->'recipients') = 'array'
                                 THEN item->'recipients'
                                 ELSE '[]'::jsonb
                            END
                        ) AS r
                    ),
                    ''
                ),
                ' '
            ),
            ''
        )
        FROM all_items
        $$ LANGUAGE SQL IMMUTABLE;
    """)

    op.execute("DROP FUNCTION IF EXISTS timeline_item_normalize(JSONB)")
    op.execute("DROP FUNCTION IF EXISTS timeline_items_to_object(JSONB)")
    op.execute("DROP FUNCTION IF EXISTS timeline_item_denormalize(JSONB)")
    op.execute("DROP FUNCTION IF EXISTS timeline_items_to_array(JSONB)")