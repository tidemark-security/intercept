import os
import re
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse

# Disable CSRF for tests (matches CI env) unless explicitly set
os.environ.setdefault("CSRF_ENABLED", "false")

import httpx
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.core.database import get_db
from app.main import app
import app.main as app_main_module

pytest_plugins = ["tests.fixtures.auth"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = PROJECT_ROOT / "dev" / "docker-compose.yml"
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/intercept_test_db",
)
BLOCKED_TEST_DATABASE_NAMES = frozenset({"intercept_case_db", "postgres", "template0", "template1"})
SAFE_TEST_DATABASE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
MAXMIND_TEST_DATA_DIR = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "maxmind"
MAXMIND_TEST_DB_FILES = [
    "GeoLite2-ASN-Test.mmdb",
    "GeoLite2-City-Test.mmdb",
    "GeoLite2-Country-Test.mmdb",
    "GeoIP2-Anonymous-IP-Test.mmdb",
    "GeoIP2-Connection-Type-Test.mmdb",
    "GeoIP2-Domain-Test.mmdb",
    "GeoIP2-Enterprise-Test.mmdb",
    "GeoIP2-ISP-Test.mmdb",
]

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


def _is_test_scoped_database_name(database_name: str) -> bool:
    return (
        database_name == "intercept_test_db"
        or database_name.startswith("test_")
        or database_name.endswith("_test")
        or database_name.endswith("_test_db")
    )


def _validate_test_database_url(database_url: str) -> str:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "Backend tests require PostgreSQL. Set TEST_DATABASE_URL to a postgresql+asyncpg URL, "
            f"got: {database_url!r}"
        )

    database_name = _extract_database_name(database_url)
    normalized_database_name = database_name.lower()
    if (
        database_name != normalized_database_name
        or not SAFE_TEST_DATABASE_NAME_RE.fullmatch(database_name)
        or normalized_database_name in BLOCKED_TEST_DATABASE_NAMES
        or not _is_test_scoped_database_name(normalized_database_name)
    ):
        raise RuntimeError(
            "Refusing to run backend tests against an unsafe database. "
            f"Parsed TEST_DATABASE_URL database name: {database_name!r}. "
            "Use a disposable test database such as "
            "'postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/intercept_test_db'."
        )

    return database_name


def _truncate_sqlmodel_tables(sync_connection) -> None:
    tables = list(SQLModel.metadata.sorted_tables)
    if not tables:
        return

    preparer = sync_connection.dialect.identifier_preparer
    table_names = ", ".join(preparer.format_table(table) for table in tables)
    sync_connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


def _download_maxmind_test_data(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for file_name in MAXMIND_TEST_DB_FILES:
            target_path = target_dir / file_name
            if target_path.exists():
                continue
            response = client.get(
                f"https://raw.githubusercontent.com/maxmind/MaxMind-DB/main/test-data/{file_name}"
            )
            response.raise_for_status()
            target_path.write_bytes(response.content)


@pytest.fixture(scope="session")
def maxmind_test_data_dir() -> Path:
    _download_maxmind_test_data(MAXMIND_TEST_DATA_DIR)
    return MAXMIND_TEST_DATA_DIR


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    _validate_test_database_url(TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL, future=True, poolclass=NullPool)
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
    if os.getenv("SKIP_DOCKER_TEST_SETUP", "").strip().lower() in {"1", "true", "yes"}:
        return

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
    if os.getenv("SKIP_DOCKER_TEST_SETUP", "").strip().lower() in {"1", "true", "yes"}:
        _validate_test_database_url(TEST_DATABASE_URL)
        return

    compose_cmd = _compose_base_command()
    database_name = _validate_test_database_url(TEST_DATABASE_URL)

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


@pytest.fixture(scope="session")
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(autouse=True)
async def clean_database_after_db_tests(request: pytest.FixtureRequest) -> AsyncGenerator[None, None]:
    uses_database = bool({"async_engine", "session_maker", "client"} & set(request.fixturenames))
    yield

    if not uses_database:
        return

    engine = request.getfixturevalue("async_engine")
    async with engine.begin() as conn:
        await conn.run_sync(_truncate_sqlmodel_tables)


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
