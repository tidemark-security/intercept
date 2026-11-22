"""Timeline search indexes introduced in v0.6.0."""

from alembic import op
import sqlalchemy as sa


TABLES = ("alerts", "cases", "tasks")
INDEX_EXPRESSIONS = (
    ("ioc_keys", "timeline_ioc_keys(timeline_items)"),
    ("timeline_text_trgm", "(timeline_items::text) gin_trgm_ops"),
)
# Both queue matching and cross-timeline correlation recheck type and field on read.
# Adding a searchable field requires rebuilding the expression indexes in a new revision.
INDEXED_FIELDS = (
    "observable_value", "value", "ip_address", "source_ip", "destination_ip",
    "contact_email", "sender", "recipient", "url", "hostname", "file_hash", "hash",
    "file_name", "process_name", "mitre_id",
)


def _entries(container: str) -> str:
    return f"""
        SELECT value FROM jsonb_each(
            CASE WHEN jsonb_typeof({container}) = 'object' THEN {container} ELSE '{{}}' END
        )
        UNION ALL
        SELECT value FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof({container}) = 'array' THEN {container} ELSE '[]' END
        )
    """


# Fixed-width keys also support long URLs. Equality on the actual field remains
# authoritative. Only replies can introduce additional timeline items.
CREATE_IOC_FUNCTION = f"""
    CREATE OR REPLACE FUNCTION timeline_ioc_keys(items jsonb) RETURNS bigint[]
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $body$
        WITH RECURSIVE entries(item) AS (
            SELECT value FROM ({_entries("items")}) AS roots
            UNION ALL
            SELECT child.value FROM entries
            CROSS JOIN LATERAL ({_entries("entries.item->'replies'")}) AS child
        )
        SELECT ARRAY(
            SELECT DISTINCT hashtextextended(lower(field.value #>> '{{}}'), 0)
            FROM entries CROSS JOIN LATERAL jsonb_each(
                CASE WHEN jsonb_typeof(item) = 'object' THEN item ELSE '{{}}' END
            ) AS field
            WHERE field.key IN ({", ".join(repr(name) for name in INDEXED_FIELDS)})
              AND field.value <> 'null'::jsonb
        )
    $body$
"""


def upgrade() -> None:
    op.execute(CREATE_IOC_FUNCTION)
    context = op.get_context()
    with context.autocommit_block():
        # PostgreSQL can JIT-compile the recursive SQL function for each row
        # while building the expression index and collecting its statistics.
        op.execute("SET jit = off")
        try:
            for table in TABLES:
                for suffix, expression in INDEX_EXPRESSIONS:
                    name = f"idx_{table}_{suffix}"
                    # Interrupted concurrent builds leave an invalid index behind.
                    if not context.as_sql and op.get_bind().scalar(sa.text(
                        "SELECT NOT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"
                    ), {"name": name}):
                        op.execute(f"DROP INDEX CONCURRENTLY {name}")
                    op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} USING gin ({expression})")
                op.execute(f"ANALYZE {table}")
        finally:
            op.execute("RESET jit")


def downgrade() -> None:
    for table in TABLES:
        for suffix, _ in INDEX_EXPRESSIONS:
            op.execute(f"DROP INDEX IF EXISTS idx_{table}_{suffix}")
    op.execute("DROP FUNCTION IF EXISTS timeline_ioc_keys(jsonb)")
