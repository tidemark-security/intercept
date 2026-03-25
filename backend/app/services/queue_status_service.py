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

        union_sql = """
            SELECT id, entrypoint, status::text AS status, priority, payload,
                   created, updated, heartbeat AS picked_at,
                   NULL::timestamptz AS finished_at,
                   NULL::int AS duration_ms,
                   NULL::text AS traceback
            FROM pgqueuer
            UNION ALL
            SELECT id, entrypoint, status, priority, payload,
                   created, updated, picked_at, finished_at,
                   duration_ms, traceback
            FROM collapsed_log
        """

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
