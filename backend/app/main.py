from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from fastapi_pagination import add_pagination
from fastapi_pagination.cursor import CursorParams

from app.core.settings_registry import get_local
from app.core.database import test_db_connection
from app.core.database import async_session_factory
from app.core.security import initialize_encryption_service
from app.services.task_queue_service import initialize_task_queue_service, shutdown_task_queue_service
from app.services.enrichment.providers import register_providers
from app.services.tasks import register_task_handlers
from app.api.routes import admin_auth, alerts, auth, cases, dashboard, dummy_data, link_templates, mitre, tasks, settings as settings_routes, langflow, api_keys, soc_metrics, triage_recommendations, search, validation, features, oidc, enrichments
# from app.api.routes import admin_auth, alerts, auth, cases, dashboard, dummy_data, link_templates, mitre, soc_metrics, tasks, api_keys
# Import models to register them with SQLModel
from app.models import models

# Configure logging
logging.basicConfig(
    level=getattr(logging, get_local("log_level").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Tidemark Intercept...")
    
    # Initialize encryption service
    logger.info("Initializing encryption service...")
    initialize_encryption_service(get_local("secret_key").encode())
    
    # Test database connection first
    logger.info("Testing database connection...")
    if not await test_db_connection():
        raise RuntimeError("Database connection failed - see error message above for solutions")
    
    # Initialize task queue service (for enqueueing tasks)
    # Note: The actual worker processing runs in separate worker containers
    # See worker.py and docker-compose.yml worker service
    register_providers()

    logger.info("Initializing task queue service...")
    try:
        await initialize_task_queue_service(get_local("database.url"))
        register_task_handlers()
        logger.info("✅ Task queue service initialized (enqueue-only mode)")
    except Exception as e:
        logger.warning(f"Task queue service initialization failed: {e}")
        logger.warning("Continuing without background task support")
    
    logger.info("🚀 Tidemark Intercept is ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Tidemark Intercept...")
    
    # Shutdown task queue
    try:
        await shutdown_task_queue_service()
        logger.info("✅ Task queue service shut down")
    except Exception as e:
        logger.warning(f"Task queue shutdown error: {e}")


# Create FastAPI application (without lifespan initially - will be set after MCP setup)
app = FastAPI(
    title="Tidemark Intercept",
    description="Cyber Security Case Management and Alert Triage Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=True  # Handle trailing slash redirects automatically
)

# Configure CORS
app.add_middleware(
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
    ],
    expose_headers=["*"],
)

# Include routers BEFORE MCP generation so routes are available
app.include_router(cases.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(triage_recommendations.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(oidc.router, prefix="/api/v1")
app.include_router(admin_auth.authenticated_router, prefix="/api/v1")
app.include_router(admin_auth.router, prefix="/api/v1")
app.include_router(dummy_data.router, prefix="/api/v1")
app.include_router(link_templates.router, prefix="/api/v1")
app.include_router(mitre.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(settings_routes.router, prefix="/api/v1")
app.include_router(enrichments.router, prefix="/api/v1")
app.include_router(enrichments.admin_router, prefix="/api/v1")
app.include_router(langflow.router, prefix="/api/v1")
app.include_router(soc_metrics.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(validation.router, prefix="/api/v1")
app.include_router(features.router, prefix="/api/v1")

# Add pagination support
add_pagination(app)

# Import and use explicit MCP server (replaces auto-generated from_fastapi)
# Part of T014 (Phase 2: MCP Server Skeleton)
from app.mcp.server import mcp

# Create the MCP ASGI app
# Note: path="" so that when mounted at /mcp, routes become /mcp/sse and /mcp/messages
mcp_app = mcp.http_app(path="", transport="sse")


# ---------------------------------------------------------------------------
# MCP API Key Authentication Middleware
# ---------------------------------------------------------------------------

from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from app.services.api_key_service import (
    api_key_service,
    ApiKeyNotFoundError,
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    UserInactiveError,
    AuditContext,
)


def _extract_api_key_from_headers(headers: dict) -> str | None:
    """Extract API key from request headers."""
    # Check Authorization header first (Bearer token)
    auth_header = headers.get(b"authorization", b"").decode()
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    
    # Fall back to X-API-Key header
    api_key = headers.get(b"x-api-key", b"").decode()
    if api_key:
        return api_key.strip()
    
    return None


class MCPApiKeyAuthMiddleware:
    """ASGI middleware that requires API key authentication for MCP requests."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Pass through non-HTTP requests (like lifespan)
            await self.app(scope, receive, send)
            return
        
        # Extract headers as dict
        headers = dict(scope.get("headers", []))
        api_key = _extract_api_key_from_headers(headers)
        
        # Get path for logging
        path = scope.get("path", "unknown")
        
        if not api_key:
            logger.warning(f"MCP auth failed: No API key provided for {path}")
            response = JSONResponse(
                status_code=401,
                content={"message": "API key required. Use Authorization: Bearer <key> or X-API-Key header."}
            )
            await response(scope, receive, send)
            return
        
        # Validate the API key
        client_host = None
        
        try:
            async with async_session_factory() as db:
                # Build audit context
                if scope.get("client"):
                    client_host = scope["client"][0]
                user_agent = headers.get(b"user-agent", b"").decode()
                
                audit_context = AuditContext(
                    ip_address=client_host,
                    user_agent=user_agent,
                    correlation_id=headers.get(b"x-request-id", b"").decode() or None,
                )
                
                # Validate the API key
                result = await api_key_service.validate_api_key(
                    db,
                    raw_key=api_key,
                    context=audit_context,
                )
                
                # Store user in scope for potential downstream use
                scope["mcp_user"] = result.user
                
                # Log successful authentication
                logger.info(
                    f"MCP auth success: user={result.user.username}, "
                    f"user_id={result.user.id}, path={path}, ip={client_host}"
                )
                
        except ApiKeyNotFoundError:
            logger.warning(f"MCP auth failed: Invalid API key for {path}, ip={client_host}")
            response = JSONResponse(status_code=401, content={"message": "Invalid API key"})
            await response(scope, receive, send)
            return
        except ApiKeyExpiredError:
            logger.warning(f"MCP auth failed: Expired API key for {path}, ip={client_host}")
            response = JSONResponse(status_code=401, content={"message": "API key has expired"})
            await response(scope, receive, send)
            return
        except ApiKeyRevokedError:
            logger.warning(f"MCP auth failed: Revoked API key for {path}, ip={client_host}")
            response = JSONResponse(status_code=401, content={"message": "API key has been revoked"})
            await response(scope, receive, send)
            return
        except UserInactiveError:
            logger.warning(f"MCP auth failed: Inactive user for {path}, ip={client_host}")
            response = JSONResponse(status_code=403, content={"message": "User account is not active"})
            await response(scope, receive, send)
            return
        except Exception as e:
            logger.error(f"MCP auth error: {e}, path={path}, ip={client_host}", exc_info=True)
            response = JSONResponse(status_code=500, content={"message": "Authentication error"})
            await response(scope, receive, send)
            return
        
        # Auth succeeded, pass through to MCP app
        await self.app(scope, receive, send)


# Wrap MCP app with auth middleware
authenticated_mcp_app = MCPApiKeyAuthMiddleware(mcp_app)


# Combine app and MCP lifespans
@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    """Combined lifespan manager for app and MCP server."""
    async with app_lifespan(app):
        async with mcp_app.lifespan(app):
            yield


# Set the combined lifespan on the app
app.router.lifespan_context = combined_lifespan

# Mount the authenticated MCP server at /mcp
app.mount("/mcp", authenticated_mcp_app)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Tidemark Intercept API",
        "version": "1.0.0",
        "docs": "/docs",
        "mcp": "/mcp"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "intercept-case-management",
        "version": "1.0.0"
    }


@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle CORS preflight requests."""
    return {"message": "OK"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return HTTPException(
        status_code=500,
        detail="Internal server error"
    )
