import asyncio
import os
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlmodel import SQLModel

from app.core.database import get_db
from app.main import app
import app.main as app_main_module

pytest_plugins = ["tests.fixtures.auth"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/intercept_test_db",
)

if not TEST_DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        "Backend tests require PostgreSQL. Set TEST_DATABASE_URL to a postgresql+asyncpg URL, "
        f"got: {TEST_DATABASE_URL!r}"
    )


def _compose_base_command() -> list[str]:
    docker_path = shutil.which("docker")
    if docker_path is not None:
        compose_version = subprocess.run(
            [docker_path, "compose", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if compose_version.returncode == 0:
            return [docker_path, "compose"]

    docker_compose_path = shutil.which("docker-compose")
    if docker_compose_path is not None:
        return [docker_compose_path]

    raise RuntimeError(
        "Docker Compose is required for backend tests. Install either 'docker compose' plugin "
        "or 'docker-compose' binary."
    )


def _extract_database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise RuntimeError(f"TEST_DATABASE_URL does not include a database name: {database_url!r}")
    return db_name


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest_asyncio.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def ensure_postgres_container() -> None:
    """Start and wait for docker-compose postgres used by backend tests."""
    compose_cmd = _compose_base_command()

    if not COMPOSE_FILE.exists():
        raise RuntimeError(f"docker-compose file not found at {COMPOSE_FILE}")

    subprocess.run(
        [*compose_cmd, "-f", str(COMPOSE_FILE), "up", "-d", "postgres"],
        cwd=str(PROJECT_ROOT),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    timeout_seconds = 90
    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        probe = subprocess.run(
            [
                *compose_cmd,
                "-f",
                str(COMPOSE_FILE),
                "exec",
                "-T",
                "postgres",
                "pg_isready",
                "-U",
                "intercept_user",
                "-d",
                "intercept_case_db",
            ],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if probe.returncode == 0:
            return

        last_error = (probe.stderr or probe.stdout or "postgres not ready").strip()
        time.sleep(2)

    raise RuntimeError(f"Postgres did not become ready within {timeout_seconds}s: {last_error}")


@pytest.fixture(scope="session", autouse=True)
def ensure_test_database(ensure_postgres_container: None) -> None:
    compose_cmd = _compose_base_command()
    database_name = _extract_database_name(TEST_DATABASE_URL)

    exists = subprocess.run(
        [
            *compose_cmd,
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "intercept_user",
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{database_name}'",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    if exists.stdout.strip() == "1":
        return

    subprocess.run(
        [
            *compose_cmd,
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "intercept_user",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {database_name}",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


@pytest.fixture()
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture()
async def client(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _test_lifespan(app_instance):
        yield

    app.router.lifespan_context = _test_lifespan  # type: ignore[assignment]
    original_mcp_session_factory = app_main_module.async_session_factory
    app_main_module.async_session_factory = session_maker  # type: ignore[assignment]

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.pop(get_db, None)
    app_main_module.async_session_factory = original_mcp_session_factory  # type: ignore[assignment]
    app.router.lifespan_context = original_lifespan
