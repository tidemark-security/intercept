"""Session-authenticated custom dashboard definitions and record queries."""

from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.request_metadata import build_audit_context
from app.api.route_utils import read_session_cookie
from app.api.routes.admin_auth import require_shared_authentication
from app.core.csrf import extract_api_key
from app.core.database import async_session_factory, get_db
from app.models.dashboard_models import (
    CustomDashboardRead,
    DashboardDrillRequest,
    DashboardDuplicate,
    DashboardEvaluate,
    DashboardEvaluation,
    DashboardMeasure,
    DashboardRecords,
    DashboardSummary,
    DashboardUpdate,
    DashboardWrite,
)
from app.models.enums import UserRole
from app.models.models import UserAccount
from app.services import custom_dashboard_service as dashboards
from app.services import dashboard_queries
from app.services.dashboard_catalog import CATALOG

router = APIRouter(prefix="/custom-dashboards", tags=["custom-dashboards"])


def session_token(request: Request) -> str:
    token = read_session_cookie(request)
    if not token or extract_api_key(request.headers):
        raise HTTPException(status_code=401, detail="Sign in to use custom dashboards")
    return token


async def dashboard_viewer(
    _: str = Depends(session_token),
    user: UserAccount = Depends(require_shared_authentication),
) -> UserAccount:
    return user


async def reporting_session(db: AsyncSession = Depends(get_db)):
    # Auth and saved definitions use the ordinary request transaction.
    # Data queries use one consistent snapshot, including across widgets.
    bind = db.bind
    if not isinstance(bind, AsyncEngine):
        raise RuntimeError("Dashboard reads require an async engine")
    async with async_session_factory(bind=bind.execution_options(isolation_level="REPEATABLE READ")) as read_db:
        yield read_db


@contextmanager
def dashboard_errors():
    try:
        yield
    except dashboards.DashboardNotFound as exc:
        raise HTTPException(status_code=404, detail="Dashboard not found") from exc
    except dashboards.DashboardForbidden as exc:
        raise HTTPException(status_code=403, detail="You do not have permission to edit this dashboard") from exc
    except dashboards.DashboardConflict as exc:
        raise HTTPException(status_code=409, detail="The dashboard changed. Reload it or save your edits as a personal copy.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/catalog", operation_id="getDashboardCatalog")
async def get_catalog(_: UserAccount = Depends(dashboard_viewer)) -> list[DashboardMeasure]:
    return list(CATALOG.values())


@router.get("", operation_id="listCustomDashboards")
async def list_dashboards(
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> list[DashboardSummary]:
    return await dashboards.list_dashboards(db, user)


@router.post("", operation_id="createCustomDashboard", status_code=201)
async def create_dashboard(
    payload: DashboardWrite, request: Request,
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> CustomDashboardRead:
    with dashboard_errors():
        return await dashboards.create_dashboard(db, payload, user, build_audit_context(request))


@router.post("/evaluate", operation_id="evaluateCustomDashboard")
async def evaluate_dashboard(
    payload: DashboardEvaluate,
    token: str = Depends(session_token), db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(dashboard_viewer), read_db: AsyncSession = Depends(reporting_session),
) -> DashboardEvaluation:
    with dashboard_errors():
        definition = await dashboards.evaluation_definition(db, payload, user)
        return await dashboard_queries.evaluate(read_db, payload.model_copy(update={"definition": definition}), user, token)


@router.post("/records", operation_id="getDashboardRecords")
async def drill_dashboard(
    payload: DashboardDrillRequest, token: str = Depends(session_token),
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
    read_db: AsyncSession = Depends(reporting_session),
) -> DashboardRecords:
    with dashboard_errors():
        context = dashboard_queries.decode_drill(payload.reference, token, user)
        if context.dashboard_id is not None:
            source = await dashboards.get_dashboard(db, context.dashboard_id, user)
            if source.revision != context.revision:
                raise dashboards.DashboardConflict()
        elif user.role == UserRole.AUDITOR:
            raise dashboards.DashboardForbidden()
        try:
            return await dashboard_queries.drill(read_db, context, user, payload.page)
        except DBAPIError as exc:
            raise HTTPException(status_code=503, detail="Could not load the matching records. Try again.") from exc


@router.get("/{identifier}", operation_id="getCustomDashboard")
async def get_dashboard(
    identifier: str, db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> CustomDashboardRead:
    with dashboard_errors():
        return await dashboards.get_dashboard(db, identifier, user)


@router.put("/{identifier}", operation_id="updateCustomDashboard")
async def update_dashboard(
    identifier: str, payload: DashboardUpdate, request: Request,
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> CustomDashboardRead:
    with dashboard_errors():
        return await dashboards.update_dashboard(db, identifier, payload, user, build_audit_context(request))


@router.post("/{identifier}/duplicate", operation_id="duplicateCustomDashboard", status_code=201)
async def duplicate_dashboard(
    identifier: str, payload: DashboardDuplicate, request: Request,
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> CustomDashboardRead:
    with dashboard_errors():
        return await dashboards.duplicate_dashboard(db, identifier, payload.title, user, build_audit_context(request))


@router.delete("/{identifier}", operation_id="deleteCustomDashboard", status_code=204)
async def delete_dashboard(
    identifier: str, request: Request, revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db), user: UserAccount = Depends(dashboard_viewer),
) -> Response:
    with dashboard_errors():
        await dashboards.delete_dashboard(db, identifier, revision, user, build_audit_context(request))
    return Response(status_code=204)
