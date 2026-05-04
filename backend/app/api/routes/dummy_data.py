"""
API routes for dummy data generation and management.
These endpoints are intended for development and testing purposes only.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.services.dummy_data_service import dummy_data_service
from app.api.routes.admin_auth import (
    require_authenticated_user,
    require_non_auditor_user,
)

router = APIRouter(
    prefix="/dummy-data",
    tags=["dummy-data"],
)


@router.post(
    "/populate",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_non_auditor_user)],
)
async def populate_dummy_data(
    cases_count: int = Query(10, ge=1, description="Number of cases to create"),
    alerts_count: int = Query(
        20,
        ge=1,
        description="Number of random alerts to create (closure-prone alerts are added automatically)",
    ),
    link_alerts: bool = Query(True, description="Whether to link some alerts to cases"),
    db: AsyncSession = Depends(get_db),
):
    """
    Populate the database with randomized dummy data for development and testing.

    This endpoint creates realistic test data including:
    - Cases with randomized titles, descriptions, statuses, and timeline items
    - Alerts with various severities, statuses, and indicators
    - Relationships between some alerts and cases

    **Warning**: This is intended for development environments only.
    """
    try:
        result = await dummy_data_service.populate_dummy_data(
            db=db,
            cases_count=cases_count,
            alerts_count=alerts_count,
            link_some_alerts=link_alerts,
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error populating dummy data")
        raise HTTPException(status_code=500, detail="Error populating dummy data")


@router.delete(
    "/clear",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_non_auditor_user)],
)
async def clear_all_data(
    confirm: bool = Query(False, description="Must be true to confirm data deletion"),
    db: AsyncSession = Depends(get_db),
):
    """
    Clear dummy data (tagged with ``tmi_dummy_data``) from the database.

    **Only** cases, alerts, tasks, and related audit logs that were created
    by the dummy-data service are removed.  User-created data is untouched.

    Requires confirmation parameter to be set to true.
    """
    if not confirm:
        raise HTTPException(
            status_code=400, detail="Must set confirm=true to clear all data"
        )

    try:
        result = await dummy_data_service.clear_all_data(db)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error clearing data")
        raise HTTPException(status_code=500, detail="Error clearing data")


@router.post(
    "/generate-cases",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_non_auditor_user)],
)
async def generate_cases_only(
    count: int = Query(5, ge=1, le=50, description="Number of cases to create"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate only cases with timeline items (no alerts).

    Useful for testing case-specific functionality without cluttering
    the alerts list.
    """
    try:
        cases = await dummy_data_service.generate_cases(db, count)

        return {
            "success": True,
            "message": f"Generated {len(cases)} cases successfully",
            "data": {
                "cases_created": len(cases),
                "case_ids": [case.id for case in cases],
            },
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating cases")
        raise HTTPException(status_code=500, detail="Error generating cases")


@router.post(
    "/generate-alerts",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_non_auditor_user)],
)
async def generate_alerts_only(
    count: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of random alerts to create (closure-prone alerts are added automatically)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate only alerts (not linked to cases).

    Useful for testing alert triage functionality and alert list views.
    """
    try:
        alerts = await dummy_data_service.generate_alerts(db, count)

        closure_count = dummy_data_service.CLOSURE_PRONE_ALERT_DEFAULT_COUNT
        random_count = max(0, len(alerts) - closure_count)

        return {
            "success": True,
            "message": f"Generated {len(alerts)} alerts successfully",
            "data": {
                "alerts_created": len(alerts),
                "random_alerts_created": random_count,
                "closure_prone_alerts_created": min(len(alerts), closure_count),
                "alert_ids": [alert.id for alert in alerts],
            },
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating alerts")
        raise HTTPException(status_code=500, detail="Error generating alerts")


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_authenticated_user)],
)
async def get_data_stats(db: AsyncSession = Depends(get_db)):
    """
    Get statistics about current data in the database.

    Returns counts of cases, alerts, and their relationships.
    """
    try:
        # Get counts using raw SQL for efficiency
        from sqlalchemy import text

        case_count_result = await db.execute(text("SELECT COUNT(*) FROM cases"))
        case_count = case_count_result.scalar()

        alert_count_result = await db.execute(text("SELECT COUNT(*) FROM alerts"))
        alert_count = alert_count_result.scalar()

        linked_alerts_result = await db.execute(
            text("SELECT COUNT(*) FROM alerts WHERE case_id IS NOT NULL")
        )
        linked_alerts_count = linked_alerts_result.scalar()

        # Get status distributions
        case_status_result = await db.execute(
            text("SELECT status, COUNT(*) FROM cases GROUP BY status")
        )
        case_statuses = dict(case_status_result.fetchall())

        alert_status_result = await db.execute(
            text("SELECT status, COUNT(*) FROM alerts GROUP BY status")
        )
        alert_statuses = dict(alert_status_result.fetchall())

        return {
            "success": True,
            "data": {
                "total_cases": case_count,
                "total_alerts": alert_count,
                "linked_alerts": linked_alerts_count,
                "unlinked_alerts": alert_count - linked_alerts_count,
                "case_status_distribution": case_statuses,
                "alert_status_distribution": alert_statuses,
            },
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting data stats")
        raise HTTPException(status_code=500, detail="Error getting data stats")
