from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
from typing import AsyncGenerator
import logging
from app.core.settings_registry import get_local

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    get_local("database.url"),
    echo=True,  # Set to False in production
    future=True
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
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
        finally:
            await session.close()


async def test_db_connection():
    """Test database connection and provide helpful error messages."""
    try:
        async with engine.begin() as conn:
            # Simple test query
            result = await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful!")
            return True
    except (OperationalError, ConnectionRefusedError, OSError) as e:
        error_msg = (
            "\n" + "="*80 + "\n"
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
            f"Database URL: {get_local('database.url')}\n"
            f"Error details: {str(e)}\n"
            "="*80
        )
        logger.error(error_msg)
        return False
