"""Intercept's HTTP composition and worker startup lifecycle."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from fastapi_pagination import add_pagination
from fastapi_pagination.cursor import CursorParams  # noqa: F401 - pagination model registration
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from app.api.routes import (
    admin_auth,
    alerts,
    api_keys,
    audit,
    auth,
    case_runbooks,
    cases,
    context_entries,
    dashboard,
    dummy_data,
    enrichments,
    features,
    langflow,
    link_templates,
    mcp_oauth,
    mitre,
    oidc,
    queue_status,
    search,
    settings as settings_routes,
    soc_metrics,
    tasks,
    triage_recommendations,
    validation,
)
from app.api.routes import websocket as ws_route
from app.api.routes.admin_auth import (
    require_admin_user,
    require_authenticated_user,
    require_non_auditor_user,
)
from app.core.csrf import CSRFMiddleware
from app.core.database import async_session_factory, engine, test_db_connection
from app.core.security import initialize_encryption_service
from app.core.settings_registry import get_local
from app.mcp.runtime import build_mcp_runtime, load_mcp_auth_snapshot
from app.mcp.server import mcp  # schema-only server retained for code/tests importing it
from app.models import models  # noqa: F401 - register SQLModel metadata
from app.services.enrichment.providers import register_providers
from app.services.settings_service import SettingsService
from app.services.task_queue_service import (
    initialize_task_queue_service,
    shutdown_task_queue_service,
)
from app.services.tasks import register_task_handlers


def _read_version() -> str:
    env_ver = os.environ.get("APP_VERSION")
    if env_ver:
        return env_ver
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.is_file():
        return version_file.read_text().strip()
    return "dev"


APP_VERSION = _read_version()

logging.basicConfig(
    level=getattr(logging, get_local("log_level").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """Initialize and close Intercept's non-MCP application resources."""

    logger.info("Starting Tidemark Intercept...")
    initialize_encryption_service(get_local("secret_key").encode())
    if not await test_db_connection():
        raise RuntimeError(
            "Database connection failed - see error message above for solutions"
        )

    register_providers()
    try:
        await initialize_task_queue_service(get_local("database.url"))
        await register_task_handlers()
        logger.info("Task queue service initialized (enqueue-only mode)")
    except Exception as exc:
        logger.warning("Continuing without background task support: %s", exc)

    from app.services.realtime_service import notification_listener

    try:
        await notification_listener.start()
        logger.info("Real-time notification listener started")
    except Exception as exc:
        logger.warning("Continuing without real-time notifications: %s", exc)

    try:
        yield
    finally:
        logger.info("Shutting down Tidemark Intercept...")
        try:
            await notification_listener.stop()
        except Exception as exc:
            logger.warning("Notification listener shutdown error: %s", exc)
        try:
            await shutdown_task_queue_service()
        except Exception as exc:
            logger.warning("Task queue shutdown error: %s", exc)


api_app = FastAPI(
    title="Tidemark Intercept",
    description="Cyber Security Case Management and Alert Triage Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=True,
)


AUTH_DEPENDENCIES = {
    require_authenticated_user,
    require_admin_user,
    require_non_auditor_user,
}


def _has_auth_dependency(dependant: Any) -> bool:
    return any(
        dependency.call in AUTH_DEPENDENCIES
        or _has_auth_dependency(dependency)
        for dependency in dependant.dependencies
    )


def custom_openapi() -> dict[str, Any]:
    if api_app.openapi_schema:
        return api_app.openapi_schema

    schema = get_openapi(
        title=api_app.title,
        version=api_app.version,
        description=api_app.description,
        routes=api_app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "BearerAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "API Key",
        "description": (
            "Enter a Tidemark API key. Swagger sends it as Authorization: Bearer <key>."
        ),
    }
    for route in api_app.routes:
        if not isinstance(route, APIRoute) or not _has_auth_dependency(route.dependant):
            continue
        path_item = schema.get("paths", {}).get(route.path_format)
        if not path_item:
            continue
        for method in route.methods:
            operation = path_item.get(method.lower())
            if operation is not None:
                operation["security"] = [{"BearerAuth": []}]

    api_app.openapi_schema = schema
    return schema


api_app.openapi = custom_openapi
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=get_local("cors_origins"),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-CSRF-Token",
        "X-XSRF-TOKEN",
    ],
    expose_headers=["*"],
)
api_app.add_middleware(
    CSRFMiddleware,
    session_factory_provider=lambda: async_session_factory,
)

api_app.include_router(cases.router, prefix="/api/v1")
api_app.include_router(case_runbooks.router, prefix="/api/v1")
api_app.include_router(alerts.router, prefix="/api/v1")
api_app.include_router(triage_recommendations.router, prefix="/api/v1")
api_app.include_router(context_entries.router, prefix="/api/v1")
api_app.include_router(tasks.router, prefix="/api/v1")
api_app.include_router(auth.router, prefix="/api/v1")
api_app.include_router(oidc.router, prefix="/api/v1")
api_app.include_router(admin_auth.authenticated_router, prefix="/api/v1")
api_app.include_router(admin_auth.router, prefix="/api/v1")
api_app.include_router(audit.router, prefix="/api/v1")
api_app.include_router(dummy_data.router, prefix="/api/v1")
api_app.include_router(link_templates.router, prefix="/api/v1")
api_app.include_router(link_templates.personal_router, prefix="/api/v1")
api_app.include_router(mitre.router, prefix="/api/v1")
api_app.include_router(dashboard.router, prefix="/api/v1")
api_app.include_router(settings_routes.authenticated_router, prefix="/api/v1")
api_app.include_router(settings_routes.router, prefix="/api/v1")
api_app.include_router(enrichments.router, prefix="/api/v1")
api_app.include_router(enrichments.admin_router, prefix="/api/v1")
api_app.include_router(queue_status.router, prefix="/api/v1")
api_app.include_router(langflow.router, prefix="/api/v1")
api_app.include_router(soc_metrics.router, prefix="/api/v1")
api_app.include_router(api_keys.router, prefix="/api/v1")
api_app.include_router(mcp_oauth.consent_router, prefix="/api/v1")
api_app.include_router(mcp_oauth.management_router, prefix="/api/v1")
api_app.include_router(search.router, prefix="/api/v1")
api_app.include_router(validation.router, prefix="/api/v1")
api_app.include_router(features.router, prefix="/api/v1")
api_app.include_router(ws_route.router, prefix="/api/v1")
add_pagination(api_app)


@api_app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Tidemark Intercept API",
        "version": APP_VERSION,
        "docs": "/docs",
        "mcp": "/mcp/streamable/",
    }


@api_app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "intercept-case-management",
        "version": APP_VERSION,
    }


@api_app.options("/{path:path}")
async def options_handler(path: str) -> dict[str, str]:
    _ = path
    return {"message": "OK"}


@api_app.exception_handler(Exception)
async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    _ = request
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class RuntimeApplication:
    """Delegate HTTP to the startup-built composition while owning one lifespan."""

    def __init__(self, fallback_app: Any, lifespan: Any) -> None:
        self._fallback_app = fallback_app
        self._http_app = fallback_app
        self._lifespan_app = Starlette(lifespan=lifespan)
        self.runtime: Any | None = None

    def install(self, http_app: Any, runtime: Any) -> None:
        self._http_app = http_app
        self.runtime = runtime

    def reset(self) -> None:
        self._http_app = self._fallback_app
        self.runtime = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan_app(scope, receive, send)
            return
        await self._http_app(scope, receive, send)


def compose_http_app(existing_api_app: FastAPI, runtime: Any) -> Starlette:
    """Order discovery and MCP routes ahead of the API/SPA application."""

    return Starlette(
        routes=[
            *runtime.well_known_routes,
            Mount("/mcp", app=runtime.mounted_app),
            Mount("/", app=existing_api_app),
        ]
    )


def _local_provider_factory(snapshot: Any) -> Any:
    """Late import keeps local provider persistence out of API-only startup."""

    from app.mcp.local_oauth_provider import create_local_oauth_provider

    return create_local_oauth_provider(
        snapshot=snapshot,
        session_factory=async_session_factory,
    )


@asynccontextmanager
async def outer_lifespan(_lifespan_app: Starlette):
    """Build auth topology before FastMCP captures routes and middleware."""

    async with app_lifespan(api_app):
        async with async_session_factory() as db:
            snapshot = await load_mcp_auth_snapshot(SettingsService(db))

        database_url = engine.url.render_as_string(hide_password=False)
        runtime = await build_mcp_runtime(
            snapshot=snapshot,
            database_url=database_url,
            secret_key=str(get_local("secret_key")),
            session_factory=async_session_factory,
            local_provider_factory=_local_provider_factory,
        )
        composed = compose_http_app(api_app, runtime)
        api_app.state.mcp_runtime = runtime
        app.install(composed, runtime)
        try:
            async with runtime.http_app.lifespan(runtime.http_app):
                logger.info(
                    "MCP ready: mode=%s resource=%s",
                    snapshot.mode.value,
                    snapshot.resource_url,
                )
                yield
        finally:
            app.reset()
            api_app.state.mcp_runtime = None


app = RuntimeApplication(api_app, outer_lifespan)


__all__ = [
    "api_app",
    "app",
    "app_lifespan",
    "compose_http_app",
    "mcp",
    "outer_lifespan",
]
