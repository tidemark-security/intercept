"""Run a migration operation on the test's current PostgreSQL connection."""

from collections.abc import Callable

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection


def run_migration(connection: Connection, operation: Callable[[], None]) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        operation()
