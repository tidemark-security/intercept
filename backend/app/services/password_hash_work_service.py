"""Cross-worker capacity controls for expensive password hashing work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import TypeVar
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.models.models import PasswordHashWorkLease


logger = logging.getLogger(__name__)
T = TypeVar("T")

_PASSWORD_WORK_ADVISORY_LOCK_ID = 0x544D_5057_4841


async def _defer_current_task_cancellation(
    cancellation: asyncio.CancelledError | None,
    exc: asyncio.CancelledError,
) -> asyncio.CancelledError:
    """Consume one cancellation while security-critical cleanup completes.

    Catching ``CancelledError`` does not clear the task's cancellation count.
    Leaving that count outstanding can make the next shielded wait immediately
    raise again instead of observing the worker/cleanup task's completion. Each
    intercepted request cancellation is therefore consumed here and the first
    exception is raised again after the durable lease has been released.
    """

    deferred = cancellation or exc
    task = asyncio.current_task()
    if task is not None:
        task.uncancel()

    # On Python 3.12 a caught cancellation can leave the task's internal
    # cancellation delivery pending even after ``uncancel()``. Without an
    # explicit cooperative yield, a loop of newly-created shield futures can
    # then raise immediately and starve the callback that marks the underlying
    # executor/cleanup future done. Yield until the task can make one normal
    # scheduling turn, consuming any additional cancellations on the way.
    while True:
        try:
            await asyncio.sleep(0)
            return deferred
        except asyncio.CancelledError as next_exc:
            deferred = deferred or next_exc
            if task is not None:
                task.uncancel()


@dataclass(frozen=True, slots=True)
class PasswordHashWorkPolicy:
    max_concurrent: int
    lease_seconds: int
    retry_after_seconds: int = 30


class PasswordHashWorkCapacityError(RuntimeError):
    """Raised when global Argon2 capacity is already reserved."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__("Password hashing capacity is full; retry later")
        self.retry_after_seconds = max(1, int(retry_after_seconds))


class PasswordHashWorkService:
    """Reserve durable global leases and enforce a local executor cap."""

    def __init__(self) -> None:
        self._default_policy = PasswordHashWorkPolicy(
            max_concurrent=max(
                1,
                int(get_local("auth.password_work.max_concurrent")),
            ),
            lease_seconds=max(
                1,
                int(get_local("auth.password_work.lease_seconds")),
            ),
        )
        self._local_semaphores: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            asyncio.Semaphore,
        ] = WeakKeyDictionary()

    @property
    def default_policy(self) -> PasswordHashWorkPolicy:
        return self._default_policy

    def _local_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        semaphore = self._local_semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._default_policy.max_concurrent)
            self._local_semaphores[loop] = semaphore
        return semaphore

    async def reserve(
        self,
        db: AsyncSession,
        *,
        work_kind: str,
        policy: PasswordHashWorkPolicy | None = None,
    ) -> UUID:
        """Reserve one global slot in the caller's current transaction."""

        effective = policy or self._default_policy
        max_concurrent = max(1, int(effective.max_concurrent))
        lease_seconds = max(1, int(effective.lease_seconds))
        now = datetime.now(timezone.utc)

        await db.execute(
            select(func.pg_advisory_xact_lock(_PASSWORD_WORK_ADVISORY_LOCK_ID))
        )
        await db.execute(
            delete(PasswordHashWorkLease).where(
                PasswordHashWorkLease.expires_at <= now
            )
        )
        active = await db.scalar(
            select(func.count()).select_from(PasswordHashWorkLease)
        )
        if int(active or 0) >= max_concurrent:
            raise PasswordHashWorkCapacityError(
                retry_after_seconds=min(
                    lease_seconds,
                    max(1, int(effective.retry_after_seconds)),
                )
            )

        lease = PasswordHashWorkLease(
            work_kind=work_kind[:32],
            created_at=now,
            expires_at=now + timedelta(seconds=lease_seconds),
        )
        db.add(lease)
        await db.flush()
        return lease.id

    async def release(self, db: AsyncSession, *, lease_id: UUID) -> None:
        await db.execute(
            delete(PasswordHashWorkLease).where(
                PasswordHashWorkLease.id == lease_id
            )
        )
        await db.commit()

    async def run_reserved(
        self,
        db: AsyncSession,
        *,
        lease_id: UUID,
        operation: Callable[[], T],
    ) -> T:
        """Run synchronous hash work and release only after its thread exits.

        The executor future is shielded. If the request is cancelled, this
        coroutine keeps waiting for the underlying thread before releasing the
        durable lease, so disconnect storms cannot manufacture extra capacity.
        """

        cancellation: asyncio.CancelledError | None = None
        result: T
        worker_error: BaseException | None = None
        try:
            async with self._local_semaphore():
                loop = asyncio.get_running_loop()
                future = loop.run_in_executor(None, operation)
                while not future.done():
                    try:
                        await asyncio.shield(future)
                    except asyncio.CancelledError as exc:
                        if not future.cancelled():
                            cancellation = await _defer_current_task_cancellation(
                                cancellation,
                                exc,
                            )
                    except BaseException:
                        pass
                try:
                    result = future.result()
                except BaseException as exc:
                    worker_error = exc
        except asyncio.CancelledError as exc:
            # Cancellation while waiting for the local semaphore happens before
            # an executor future exists, but the committed global lease still
            # belongs to this coroutine and must be released below.
            cancellation = await _defer_current_task_cancellation(cancellation, exc)
        finally:
            release_task = asyncio.create_task(
                self.release(db, lease_id=lease_id)
            )
            while not release_task.done():
                try:
                    await asyncio.shield(release_task)
                except asyncio.CancelledError as exc:
                    if not release_task.cancelled():
                        cancellation = await _defer_current_task_cancellation(
                            cancellation,
                            exc,
                        )
                except BaseException:
                    pass
            release_task.result()

        if cancellation is not None:
            if worker_error is not None:
                logger.warning(
                    "Password hash worker failed after its request was cancelled",
                    exc_info=(
                        type(worker_error),
                        worker_error,
                        worker_error.__traceback__,
                    ),
                )
            raise cancellation
        if worker_error is not None:
            raise worker_error
        return result

    async def reserve_commit_and_run(
        self,
        db: AsyncSession,
        *,
        work_kind: str,
        operation: Callable[[], T],
        policy: PasswordHashWorkPolicy | None = None,
    ) -> T:
        """Atomically hand a committed durable lease to the executor runner.

        The reservation commit is shielded and allowed to reach a definitive
        outcome. A failed commit is rolled back and cleaned; a successful commit
        observed after request cancellation is deleted before cancellation is
        propagated. With no cancellation, there is no await between the commit
        outcome and entering ``run_reserved``, whose outer ``finally`` owns
        lease cleanup even while waiting for the local semaphore.
        """

        try:
            lease_id = await self.reserve(
                db,
                work_kind=work_kind,
                policy=policy,
            )
        except PasswordHashWorkCapacityError:
            # Persist expired-lease cleanup and release the global advisory lock.
            await db.commit()
            raise

        # The commit must reach a definitive outcome before cleanup. Cancelling
        # the driver call directly is ambiguous: PostgreSQL may still commit
        # after a cleanup transaction has already looked for (and missed) the
        # lease row.
        cancellation: asyncio.CancelledError | None = None
        commit_error: BaseException | None = None
        commit_task = asyncio.create_task(db.commit())
        while not commit_task.done():
            try:
                await asyncio.shield(commit_task)
            except asyncio.CancelledError as exc:
                # A cancelled commit task is the commit's own outcome. Any
                # other cancellation belongs to this request and is deferred
                # until the commit and cleanup have completed.
                if not commit_task.cancelled():
                    cancellation = await _defer_current_task_cancellation(
                        cancellation,
                        exc,
                    )
            except BaseException:
                # Retrieve and preserve the commit's exact exception below.
                pass
        try:
            commit_task.result()
        except BaseException as exc:
            commit_error = exc

        if commit_error is not None:
            cleanup_task = asyncio.create_task(
                self._cleanup_before_worker(db, lease_id=lease_id)
            )
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError as exc:
                    if not cleanup_task.cancelled():
                        cancellation = await _defer_current_task_cancellation(
                            cancellation,
                            exc,
                        )
                except BaseException:
                    pass
            cleanup_task.result()
            if cancellation is not None:
                logger.warning(
                    "Password-work reservation commit failed after request cancellation",
                    exc_info=(
                        type(commit_error),
                        commit_error,
                        commit_error.__traceback__,
                    ),
                )
                raise cancellation
            raise commit_error

        if cancellation is not None:
            # The lease is now definitely visible. Remove it before propagating
            # cancellation because no executor worker will own its cleanup.
            cleanup_task = asyncio.create_task(
                self._cleanup_before_worker(db, lease_id=lease_id)
            )
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError as exc:
                    if not cleanup_task.cancelled():
                        cancellation = await _defer_current_task_cancellation(
                            cancellation,
                            exc,
                        )
                except BaseException:
                    pass
            cleanup_task.result()
            raise cancellation

        return await self.run_reserved(
            db,
            lease_id=lease_id,
            operation=operation,
        )

    async def _cleanup_before_worker(
        self,
        db: AsyncSession,
        *,
        lease_id: UUID,
    ) -> None:
        """Remove a reservation that will not be handed to a worker."""

        try:
            await db.rollback()
            await self.release(db, lease_id=lease_id)
            return
        except Exception:
            logger.warning(
                "Primary session could not clean an unowned password-work lease",
                exc_info=True,
            )

        # A failed primary DELETE/COMMIT can retain a row lock. Clear that
        # transaction before the independent recovery transaction attempts the
        # same lease.
        try:
            await db.rollback()
        except Exception:
            logger.warning(
                "Primary session rollback failed during password-work recovery",
                exc_info=True,
            )

        # A cancelled driver commit can invalidate its connection even when the
        # server committed. Use an independent short transaction as recovery.
        from app.core.database import async_session_factory

        async with async_session_factory() as cleanup_db:
            await self.release(cleanup_db, lease_id=lease_id)


password_hash_work_service = PasswordHashWorkService()


__all__ = [
    "PasswordHashWorkCapacityError",
    "PasswordHashWorkPolicy",
    "PasswordHashWorkService",
    "password_hash_work_service",
]
