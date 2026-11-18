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
from app.services.date_filter_utils import parse_utc_datetime

logger = logging.getLogger(__name__)


def _parse_payload(raw: Any) -> Optional[Dict[str, Any]]:
    """Safely decode a pgqueuer payload (stored as bytea) into a dict."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (bytes, bytearray, memoryview)):
            decoded = json.loads(bytes(raw))
        elif isinstance(raw, str):
            decoded = json.loads(raw)
        else:
            return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _safe_failure_summary(raw: Any) -> Optional[str]:
    """Return a bounded exception type without exposing stored traceback details."""
    if not raw:
        return None
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return "Task failed"
    if not isinstance(decoded, dict):
        return "Task failed"

    exception_type = decoded.get("exception_type")
    if not isinstance(exception_type, str):
        return "Task failed"
    normalized = "".join(
        character
        for character in exception_type.strip()
        if character.isalnum() or character in {"_", "."}
    )[:200]
    return f"Task failed ({normalized})" if normalized else "Task failed"


def _build_collapsed_log_cte(*, log_where_sql: str = "") -> str:
    """Collapse pgqueuer status-transition rows into one row per job."""
    return f"""
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
                (EXTRACT(EPOCH FROM (
                    max(created) FILTER (WHERE status IN ('successful', 'exception', 'canceled'))
                    - max(created) FILTER (WHERE status = 'picked')
                )) * 1000)::int AS duration_ms,
                max(traceback::text) FILTER (WHERE status = 'exception') AS traceback
            FROM pgqueuer_log
            {log_where_sql}
            GROUP BY job_id, entrypoint
        )
    """


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


_DEFAULT_PAYLOAD = object()


def _queue_job_from_row(row: Any, *, payload: Any = _DEFAULT_PAYLOAD) -> QueueJobRead:
    return QueueJobRead(
        id=row.id,
        entrypoint=row.entrypoint,
        status=row.status,
        priority=row.priority,
        payload=_parse_payload(row.payload) if payload is _DEFAULT_PAYLOAD else payload,
        created=row.created,
        updated=row.updated,
        picked_at=row.picked_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        traceback=_safe_failure_summary(row.traceback),
    )


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
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
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
        start_at = parse_utc_datetime(start_date) if start_date is not None else None
        end_at = parse_utc_datetime(end_date) if end_date is not None else None

        if not await self._has_pgqueuer_tables():
            return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}

        collapsed_log_cte = _build_collapsed_log_cte()

        # Build WHERE clauses and params
        where_clauses: List[str] = []
        params: Dict[str, Any] = {}

        if entrypoint:
            where_clauses.append("q.entrypoint = :entrypoint")
            params["entrypoint"] = entrypoint

        if status:
            where_clauses.append("q.status = :status")
            params["status"] = status

        if start_at is not None:
            where_clauses.append("q.created >= CAST(:start_date AS timestamptz)")
            params["start_date"] = start_at

        if end_at is not None:
            where_clauses.append("q.created <= CAST(:end_date AS timestamptz)")
            params["end_date"] = end_at

        where_sql = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

        union_sql = _build_job_union_sql()

        # Count query
        count_sql = text(
            f"WITH {collapsed_log_cte} "
            f"SELECT count(*) FROM ({union_sql}) q WHERE 1=1{where_sql}"
        )
        total = (await self.db.execute(count_sql, params)).scalar() or 0

        pages = -(-total // size) if total else 0

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

        items = [_queue_job_from_row(row) for row in rows]

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

        collapsed_log_cte = _build_collapsed_log_cte(
            log_where_sql="WHERE entrypoint = 'enrich_item'",
        )

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

            job = _queue_job_from_row(row, payload=payload)

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
