from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

from cachetools import TTLCache
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction
from sqlmodel import select

from app.models.models import EnrichmentCacheEntry
from app.services.date_filter_utils import parse_optional_utc_datetime


_PENDING_HOT_CACHE_ACTIONS = "enrichment.pending_hot_cache_actions"
_COMMITTED_HOT_CACHE_TRANSACTIONS = "enrichment.committed_hot_cache_transactions"
_NO_PENDING_VALUE = object()


@dataclass(frozen=True)
class _DeferredHotCacheAction:
    """A transaction-local view change plus its post-commit side effect."""

    apply: Callable[[], None]
    value: Dict[str, Any] | None
    key: str | None = None
    prefix: str | None = None

    def matches(self, hot_key: str) -> bool:
        if self.key is not None:
            return self.key == hot_key
        if self.prefix is not None:
            return hot_key.startswith(self.prefix)
        return True


def _current_transaction(session: Session) -> SessionTransaction | None:
    return session.get_nested_transaction() or session.get_transaction()


def _defer_hot_cache_action(db: AsyncSession, action: _DeferredHotCacheAction) -> None:
    """Apply process-local cache state only after its DB transaction commits."""
    session = db.sync_session
    transaction = _current_transaction(session)
    if transaction is None:
        raise RuntimeError("Cannot defer hot-cache state without an active transaction")

    pending = session.info.setdefault(_PENDING_HOT_CACHE_ACTIONS, {})
    pending.setdefault(transaction, []).append(action)


def _pending_hot_cache_value(db: AsyncSession, hot_key: str) -> object:
    """Return this transaction's latest logical value for a hot-cache key."""
    session = db.sync_session
    pending = session.info.get(_PENDING_HOT_CACHE_ACTIONS, {})
    transaction = _current_transaction(session)

    while transaction is not None:
        for action in reversed(pending.get(transaction, [])):
            if action.matches(hot_key):
                return action.value
        transaction = transaction.parent

    return _NO_PENDING_VALUE


@event.listens_for(Session, "after_commit")
def _mark_hot_cache_transaction_committed(session: Session) -> None:
    pending = session.info.get(_PENDING_HOT_CACHE_ACTIONS)
    transaction = _current_transaction(session)
    if pending and transaction in pending:
        committed = session.info.setdefault(_COMMITTED_HOT_CACHE_TRANSACTIONS, set())
        committed.add(transaction)


@event.listens_for(Session, "after_transaction_end")
def _complete_hot_cache_transaction(
    session: Session,
    transaction: SessionTransaction,
) -> None:
    pending = session.info.get(_PENDING_HOT_CACHE_ACTIONS)
    if not pending:
        return

    actions = pending.pop(transaction, [])
    committed = session.info.get(_COMMITTED_HOT_CACHE_TRANSACTIONS, set())
    transaction_committed = transaction in committed
    committed.discard(transaction)

    if actions and transaction_committed:
        if transaction.parent is None:
            for action in actions:
                action.apply()
        else:
            pending.setdefault(transaction.parent, []).extend(actions)

    if not pending:
        session.info.pop(_PENDING_HOT_CACHE_ACTIONS, None)
    if not committed:
        session.info.pop(_COMMITTED_HOT_CACHE_TRANSACTIONS, None)


class EnrichmentCache:
    """Two-tier enrichment cache: process-local hot cache backed by Postgres."""

    def __init__(self) -> None:
        self._maxsize = 1024
        self._ttl = 86400
        self._cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=self._maxsize, ttl=self._ttl)

    def configure(self, *, maxsize: int, ttl_seconds: int) -> None:
        maxsize = max(1, maxsize)
        ttl_seconds = max(60, ttl_seconds)
        if maxsize == self._maxsize and ttl_seconds == self._ttl:
            return
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def _key(self, provider_id: str, cache_key: str) -> str:
        return f"{provider_id}:{cache_key}"

    def _is_expired(self, payload: Dict[str, Any]) -> bool:
        expires_at = parse_optional_utc_datetime(payload.get("expires_at"))
        return expires_at is None or expires_at <= datetime.now(timezone.utc)

    async def get(self, db: AsyncSession, provider_id: str, cache_key: str) -> Optional[Dict[str, Any]]:
        hot_key = self._key(provider_id, cache_key)
        pending_value = _pending_hot_cache_value(db, hot_key)
        if pending_value is not _NO_PENDING_VALUE:
            pending_payload = cast(Optional[Dict[str, Any]], pending_value)
            if pending_payload is None or self._is_expired(pending_payload):
                return None
            return pending_payload.get("result")

        hot_value = self._cache.get(hot_key)
        if hot_value is not None:
            if self._is_expired(hot_value):
                self._cache.pop(hot_key, None)
            else:
                return hot_value.get("result")

        result = await db.execute(
            select(EnrichmentCacheEntry).where(
                EnrichmentCacheEntry.provider_id == provider_id,
                EnrichmentCacheEntry.cache_key == cache_key,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry or entry.expires_at <= datetime.now(timezone.utc):
            return None

        self._cache[hot_key] = {
            "result": entry.result,
            "expires_at": entry.expires_at.isoformat(),
        }
        return entry.result

    async def set(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        cache_key: str,
        result_payload: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl_seconds))
        query = select(EnrichmentCacheEntry).where(
            EnrichmentCacheEntry.provider_id == provider_id,
            EnrichmentCacheEntry.cache_key == cache_key,
        )
        existing = (await db.execute(query)).scalar_one_or_none()

        if existing:
            existing.result = result_payload
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(timezone.utc)
            db.add(existing)
        else:
            db.add(
                EnrichmentCacheEntry(
                    provider_id=provider_id,
                    cache_key=cache_key,
                    result=result_payload,
                    expires_at=expires_at,
                )
            )

        hot_key = self._key(provider_id, cache_key)

        hot_value = {
            "result": result_payload,
            "expires_at": expires_at.isoformat(),
        }
        _defer_hot_cache_action(
            db,
            _DeferredHotCacheAction(
                key=hot_key,
                value=hot_value,
                apply=lambda: self._cache.__setitem__(hot_key, hot_value),
            ),
        )

    async def clear(self, db: AsyncSession, provider_id: str | None = None) -> int:
        query = select(EnrichmentCacheEntry)
        if provider_id:
            query = query.where(EnrichmentCacheEntry.provider_id == provider_id)
        rows = (await db.execute(query)).scalars().all()
        for row in rows:
            await db.delete(row)
        def clear_hot_cache() -> None:
            if provider_id:
                prefix = f"{provider_id}:"
                for key in list(self._cache.keys()):
                    if key.startswith(prefix):
                        self._cache.pop(key, None)
            else:
                self._cache.clear()

        _defer_hot_cache_action(
            db,
            _DeferredHotCacheAction(
                prefix=f"{provider_id}:" if provider_id else None,
                value=None,
                apply=clear_hot_cache,
            ),
        )
        return len(rows)


enrichment_cache = EnrichmentCache()
