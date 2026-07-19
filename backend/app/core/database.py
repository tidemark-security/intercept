import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings_registry import get_local

logger = logging.getLogger(__name__)


def _redact_database_url(database_url: str) -> str:
    """Render a database URL without credentials for diagnostics."""
    return make_url(database_url).render_as_string(hide_password=True)


_DATABASE_URL = get_local("database.url")

# Create async engine
engine = create_async_engine(
    _DATABASE_URL,
    echo=bool(get_local("database.echo", False)),
    future=True,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def test_db_connection() -> bool:
    """Test database connection and provide helpful error messages."""
    try:
        async with engine.begin() as conn:
            # Simple test query
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful!")
            return True
    except (OperationalError, OSError) as exc:
        error_msg = (
            "\n" + "=" * 80 + "\n"
            "🚨 DATABASE CONNECTION TEST FAILED!\n"
            "="*80 + "\n"
            "PostgreSQL database is not available. This is likely because:\n\n"
            "1. PostgreSQL is not running\n"
            "2. Docker container is not started\n\n"
            "To fix this, run one of the following commands:\n\n"
            "📦 Using Docker Compose (recommended):\n"
            "   cd dev && docker compose up postgres -d\n\n"
            "🐘 Using local PostgreSQL:\n"
            "   sudo systemctl start postgresql\n"
            "   # or on macOS: brew services start postgresql\n\n"
            f"Database URL: {_redact_database_url(_DATABASE_URL)}\n"
            f"Error type: {type(exc).__name__}\n"
            "=" * 80
        )
        logger.error(error_msg)
        return False
