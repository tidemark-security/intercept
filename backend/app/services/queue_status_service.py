"""
Read-only service for querying pgqueuer job tables.

pgqueuer manages its own schema (``pgqueuer`` for active jobs and
``pgqueuer_log`` for completed/failed jobs).  This service issues raw SQL
against those tables so the admin UI can display job status without
depending on pgqueuer Python internals.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import QueueJobRead, QueueStatsRead

logger = logging.getLogger(__name__)


def _parse_payload(raw: Any) -> Optional[Dict[str, Any]]:
    """Safely decode a pgqueuer payload (stored as bytea) into a dict."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (bytes, bytearray, memoryview)):
            return json.loads(bytes(raw))
        if isinstance(raw, str):
            return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def _build_job_union_sql(*, active_where_sql: str = "") -> str:
    """Combine active and historical jobs without duplicating active job ids."""
    return f"""
        SELECT id, entrypoint, status::text AS status, priority, payload,
               created, updated, heartbeat AS picked_at,
               NULL::timestamptz AS finished_at,
               NULL::int AS duration_ms,
               NULL::text AS traceback
        FROM pgqueuer active
        {active_where_sql}
        UNION ALL
        SELECT log.id, log.entrypoint, log.status, log.priority, log.payload,
               log.created, log.updated, log.picked_at, log.finished_at,
               log.duration_ms, log.traceback
        FROM collapsed_log log
        WHERE NOT EXISTS (
            SELECT 1 FROM pgqueuer active
            WHERE active.id = log.id
        )
    """


class QueueStatusService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _has_pgqueuer_tables(self) -> bool:
        """Check whether the pgqueuer schema is installed."""
        result = await self.db.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_name = 'pgqueuer'"
                ")"
            )
        )
        return bool(result.scalar())

    # ------------------------------------------------------------------
    # Jobs listing
    # ------------------------------------------------------------------

    async def get_jobs(
        self,
        *,
        entrypoint: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        size: int = 25,
    ) -> Dict[str, Any]:
        """Return a paginated, filtered list of jobs (active + logged).

        The ``pgqueuer_log`` table records one row per status transition
        (queued → picked → successful/exception).  We collapse those into
        a single row per ``job_id`` showing the *final* status, the picked
        timestamp, the finished timestamp, and duration.

        Returns a dict compatible with ``fastapi_pagination`` ``Page``:
        ``{"items": [...], "total": N, "page": P, "size": S, "pages": T}``
        """
        if not await self._has_pgqueuer_tables():
            return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}

        # ---- Collapsed log CTE ----
        # One row per job_id with the final (latest) status, first created
        # timestamp, picked timestamp, finished timestamp, and traceback.
        collapsed_log_cte = """
            collapsed_log AS (
                SELECT
                    job_id AS id,
                    entrypoint,
                    -- final status is the one with the highest log id
                    (array_agg(status ORDER BY id DESC))[1]::text AS status,
                    max(priority) AS priority,
                    NULL::bytea AS payload,
                    -- first log entry is the queue time
                    min(created) AS created,
                    max(created) AS updated,
                    -- picked timestamp
                    max(created) FILTER (WHERE status = 'picked') AS picked_at,
                    -- finished timestamp (terminal states)
                    max(created) FILTER (WHERE status IN ('successful', 'exception', 'canceled')) AS finished_at,
                    -- duration in ms from picked to finished
                    EXTRACT(EPOCH FROM (
                        max(created) FILTER (WHERE status IN ('successful', 'exception', 'canceled'))
                        - max(created) FILTER (WHERE status = 'picked')
                    ))::int * 1000 AS duration_ms,
                    -- traceback from exception entries (jsonb → text)
                    max(traceback::text) FILTER (WHERE status = 'exception') AS traceback
                FROM pgqueuer_log
                GROUP BY job_id, entrypoint
            )
        """

        # Build WHERE clauses and params
        where_clauses: List[str] = []
        params: Dict[str, Any] = {}

        if entrypoint:
            where_clauses.append("q.entrypoint = :entrypoint")
            params["entrypoint"] = entrypoint

        if status:
            where_clauses.append("q.status = :status")
            params["status"] = status

        if start_date:
            where_clauses.append("q.created >= CAST(:start_date AS timestamptz)")
            params["start_date"] = datetime.fromisoformat(start_date.replace("Z", "+00:00")) if isinstance(start_date, str) else start_date

        if end_date:
            where_clauses.append("q.created <= CAST(:end_date AS timestamptz)")
            params["end_date"] = datetime.fromisoformat(end_date.replace("Z", "+00:00")) if isinstance(end_date, str) else end_date

        where_sql = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

        union_sql = _build_job_union_sql()

        # Count query
        count_sql = text(
            f"WITH {collapsed_log_cte} "
            f"SELECT count(*) FROM ({union_sql}) q WHERE 1=1{where_sql}"
        )
        total = (await self.db.execute(count_sql, params)).scalar() or 0

        pages = max(1, -(-total // size))  # ceil division

        # Data query
        offset = (page - 1) * size
        data_sql = text(
            f"WITH {collapsed_log_cte} "
            f"SELECT q.* FROM ({union_sql}) q "
            f"WHERE 1=1{where_sql} "
            f"ORDER BY q.created DESC NULLS LAST "
            f"LIMIT :limit OFFSET :offset"
        )
        params["limit"] = size
        params["offset"] = offset

        rows = (await self.db.execute(data_sql, params)).fetchall()

        items = [
            QueueJobRead(
                id=row.id,
                entrypoint=row.entrypoint,
                status=row.status,
                priority=row.priority,
                payload=_parse_payload(row.payload),
                created=row.created,
                updated=row.updated,
                picked_at=row.picked_at,
                finished_at=row.finished_at,
                duration_ms=row.duration_ms,
                traceback=row.traceback,
            )
            for row in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> List[QueueStatsRead]:
        """Return aggregate job counts for *active* jobs (pgqueuer table)."""
        if not await self._has_pgqueuer_tables():
            return []

        result = await self.db.execute(
            text(
                "SELECT entrypoint, status::text AS status, count(*)::int AS count "
                "FROM pgqueuer "
                "GROUP BY entrypoint, status "
                "ORDER BY entrypoint, status"
            )
        )
        return [
            QueueStatsRead(entrypoint=row.entrypoint, status=row.status, count=row[2])
            for row in result.fetchall()
        ]

    # ------------------------------------------------------------------
    # Distinct entrypoints (for filter dropdown)
    # ------------------------------------------------------------------

    async def get_entrypoints(self) -> List[str]:
        """Return sorted list of distinct entrypoint names across active + log."""
        if not await self._has_pgqueuer_tables():
            return []

        result = await self.db.execute(
            text(
                "SELECT DISTINCT entrypoint FROM ("
                "  SELECT entrypoint FROM pgqueuer"
                "  UNION"
                "  SELECT entrypoint FROM pgqueuer_log"
                ") t ORDER BY entrypoint"
            )
        )
        return [row[0] for row in result.fetchall()]

    async def get_enrichment_jobs_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: int,
        item_ids: List[str],
        linked_task_ids_by_item_id: Optional[Dict[str, str]] = None,
    ) -> Dict[str, QueueJobRead]:
        """Return the best matching enrich_item job per timeline item for one entity."""
        if not item_ids or not await self._has_pgqueuer_tables():
            return {}

        linked_item_ids_by_task_id = {
            str(task_id): item_id
            for item_id, task_id in (linked_task_ids_by_item_id or {}).items()
            if item_id in item_ids and str(task_id or "").strip()
        }

        collapsed_log_cte = """
            collapsed_log AS (
                SELECT
                    job_id AS id,
                    entrypoint,
                    (array_agg(status ORDER BY id DESC))[1]::text AS status,
                    max(priority) AS priority,
                    NULL::bytea AS payload,
                    min(created) AS created,
                    max(created) AS updated,
                    max(created) FILTER (WHERE status = 'picked') AS picked_at,
                    max(created) FILTER (WHERE status IN ('successful', 'exception', 'canceled')) AS finished_at,
                    EXTRACT(EPOCH FROM (
                        max(created) FILTER (WHERE status IN ('successful', 'exception', 'canceled'))
                        - max(created) FILTER (WHERE status = 'picked')
                    ))::int * 1000 AS duration_ms,
                    max(traceback::text) FILTER (WHERE status = 'exception') AS traceback
                FROM pgqueuer_log
                WHERE entrypoint = 'enrich_item'
                GROUP BY job_id, entrypoint
            )
        """

        union_sql = _build_job_union_sql(active_where_sql="WHERE entrypoint = 'enrich_item'")

        sql = text(
            f"WITH {collapsed_log_cte} "
            f"SELECT q.* FROM ({union_sql}) q "
            "WHERE ((q.payload IS NOT NULL "
            "AND convert_from(q.payload, 'UTF8')::jsonb ->> 'entity_type' = :entity_type "
            "AND CAST(convert_from(q.payload, 'UTF8')::jsonb ->> 'entity_id' AS integer) = :entity_id "
            "AND convert_from(q.payload, 'UTF8')::jsonb ->> 'item_id' = ANY(CAST(:item_ids AS text[]))) "
            "OR (q.payload IS NULL AND CAST(q.id AS text) = ANY(CAST(:linked_task_ids AS text[])))) "
            "ORDER BY q.created DESC NULLS LAST"
        )

        rows = (
            await self.db.execute(
                sql,
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "item_ids": item_ids,
                    "linked_task_ids": list(linked_item_ids_by_task_id.keys()),
                },
            )
        ).fetchall()

        jobs_by_item_id: Dict[str, QueueJobRead] = {}
        for row in rows:
            payload = _parse_payload(row.payload)
            if payload:
                item_id = str(payload.get("item_id") or "")
            else:
                item_id = linked_item_ids_by_task_id.get(str(row.id), "")
            if not item_id:
                continue

            job = QueueJobRead(
                id=row.id,
                entrypoint=row.entrypoint,
                status=row.status,
                priority=row.priority,
                payload=payload,
                created=row.created,
                updated=row.updated,
                picked_at=row.picked_at,
                finished_at=row.finished_at,
                duration_ms=row.duration_ms,
                traceback=row.traceback,
            )

            existing = jobs_by_item_id.get(item_id)
            if existing is None or self._prefer_enrichment_job(job, existing):
                jobs_by_item_id[item_id] = job

        return jobs_by_item_id

    def _prefer_enrichment_job(self, candidate: QueueJobRead, current: QueueJobRead) -> bool:
        def rank(job: QueueJobRead) -> tuple[int, datetime]:
            timestamp = job.finished_at or job.updated or job.created or datetime.min
            if job.status == "picked":
                return (3, timestamp)
            if job.status == "queued":
                return (2, timestamp)
            return (1, timestamp)

        return rank(candidate) > rank(current)
