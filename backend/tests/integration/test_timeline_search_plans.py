"""Plan regression for selective searches with ordinary PostgreSQL planner settings."""

import pytest
from sqlalchemy import event, text

from db_migrations.v0_6_0 import timeline_search
from app.models.search_schemas import EntityType
from app.services.observable_correlation import observable_occurrences
from app.services.search_service import search_service


def _nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


async def _explain_calls(connection, operation):
    """Replay the exact count/page SELECTs and driver parameters emitted by the service."""
    statements = []

    def capture(_conn, _cursor, sql, params, _context, _many):
        if sql.lstrip().upper().startswith(("SELECT", "WITH")) and "set_config(" not in sql:
            statements.append((sql, params))

    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        result = await operation
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)
    plans = []
    for sql, params in statements:
        response = await connection.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
        plans.append(response.scalar_one()[0]["Plan"])
    return result, plans


@pytest.mark.asyncio
async def test_selective_timeline_count_page_and_occurrences_use_indexes(session_maker):
    async with session_maker() as db:
        conn = await db.connection()
        # Temp rows and indexes disappear with the session. Use entity column types
        # from the real model. Rolling back also isolates this fixture from other tests.
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await db.execute(text("CREATE TEMP TABLE alerts (LIKE public.alerts INCLUDING DEFAULTS) ON COMMIT DROP"))
        await db.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS search_vector tsvector"))
        await db.execute(text("""
            INSERT INTO alerts (id, title, status, priority, description, created_at, timeline_items, search_vector)
            SELECT i, 'Ticket ' || i, 'NEW', 'MEDIUM', 'Investigation', now(),
                jsonb_build_object(
                    's', jsonb_build_object('id','s', 'type','system',
                        'ip_address','10.0.0.3',
                        'hostname', CASE WHEN i = 7211 THEN 'rare.example.org' ELSE 'common.example.net' END,
                        'description', CASE WHEN i = 7211 THEN 'UniqueNeedleArchive' ELSE 'Routine' END),
                    'n', jsonb_build_object('id','n', 'type','network_traffic',
                        'source_ip', CASE WHEN i = 7211 THEN '192.0.2.7' ELSE '10.0.0.1' END,
                        'destination_ip', CASE WHEN i = 7211 THEN '192.0.2.7' ELSE '10.0.0.2' END)),
                to_tsvector('english', 'Ticket investigation')
            FROM generate_series(1, 12000) AS i
        """))
        existing_indexes = (
            ("search_vector", "search_vector"),
            ("title_trgm", "title gin_trgm_ops"),
            ("description_trgm", "description gin_trgm_ops"),
        )
        # Match the release migration's index build settings, then run every
        # search and EXPLAIN with the database defaults.
        await db.execute(text("SET LOCAL jit = off"))
        for suffix, expr in (*existing_indexes, *timeline_search.INDEX_EXPRESSIONS):
            await db.execute(text(f"CREATE INDEX idx_alerts_{suffix} ON alerts USING gin ({expr})"))
        await db.execute(text("ANALYZE alerts"))
        await db.execute(text("SET LOCAL jit TO DEFAULT"))

        def queue_search(query):
            return search_service.search_queue(
                db, query=query, entity_type=EntityType.ALERT, status=None, assignee=None,
                include_tags=None, exclude_tags=None, start_date=None, end_date=None,
                sort_by="created_at", sort_order="desc", skip=0, limit=20,
            )

        for query, index in (
            ("192.0.2.7", "idx_alerts_ioc_keys"),
            ("needlear", "idx_alerts_timeline_text_trgm"),
            ("*needlear*", "idx_alerts_timeline_text_trgm"),
            ("rare.example.org", "idx_alerts_timeline_text_trgm"),
        ):
            result, plans = await _explain_calls(conn, queue_search(query))
            assert result.total == 1, query
            assert [row.id for row in result.results] == [7211]
            assert len(plans) == 2  # Both count and page must stay selective.
            for plan in plans:
                _assert_indexed(plan, index)

        def occurrences(value):
            return observable_occurrences(
                db, observable_type="IP", value=value, entity_types=[EntityType.ALERT],
                start=None, end=None, skip=0, limit=20,
            )

        result, plans = await _explain_calls(conn, occurrences("192.0.2.7"))
        assert result["total"] == 1
        assert result["items"][0]["item_id"] == "n"
        assert result["items"][0]["matched_fields"] == ["destination_ip", "source_ip"]
        assert len(plans) == 1
        _assert_indexed(plans[0], "idx_alerts_ioc_keys")

        # Replacing the only matching timeline must update both expression indexes.
        await db.execute(text("""
            UPDATE alerts SET timeline_items = jsonb_build_object('n', jsonb_build_object(
                'id','n', 'type','system', 'ip_address','203.0.113.9', 'description','ReplacementToken'
            )) WHERE id = 7211
        """))
        assert (await occurrences("192.0.2.7"))["total"] == 0
        assert (await occurrences("203.0.113.9"))["total"] == 1
        assert (await queue_search("placementto")).total == 1
        result, plans = await _explain_calls(conn, queue_search("needlear"))
        assert result.total == 0
        assert len(plans) == 2  # Content count followed by fuzzy fallback count.
        _assert_indexed(plans[0], "idx_alerts_timeline_text_trgm")
        _assert_indexed(plans[1], "idx_alerts_title_trgm")


def _assert_indexed(plan, index):
    nodes = list(_nodes(plan))
    assert any(node.get("Index Name") == index for node in nodes), plan
    assert not any(
        node["Node Type"] == "Seq Scan" and node.get("Relation Name") == "alerts" for node in nodes
    ), plan
