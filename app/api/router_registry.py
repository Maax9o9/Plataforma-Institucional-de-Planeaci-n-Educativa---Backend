"""Registro único y ordenado de routers HTTP."""

from fastapi import FastAPI

from app.api.uploads_router import router as uploads_router
from app.modules.audit.api.router import router as audit_router
from app.modules.dashboards.api.router import router as dashboards_router
from app.modules.evidence_management.api.router import router as evidence_router
from app.modules.identity_access.api.router import router as identity_router
from app.modules.indicators_capture.api.router import router as captures_router
from app.modules.indicators_catalog.api.router import router as indicators_catalog_router
from app.modules.indicators_reports.api.router import router as reports_router
from app.modules.indicators_scoring.api.router import router as scoring_router
from app.modules.indicators_validation.api.router import router as validation_router
from app.modules.institutional_catalogs.api.reference_router import (
    router as reference_catalogs_router,
)
from app.modules.institutional_catalogs.api.router import router as catalogs_router
from app.modules.notifications.api.router import router as notifications_router
from app.modules.periods.api.router import router as periods_router
from app.modules.poa_planning.api.router import router as poa_planning_router
from app.modules.poa_reports.api.router import router as poa_reports_router
from app.modules.poa_tracking.api.router import router as poa_tracking_router
from app.modules.poa_validation.api.router import router as poa_validation_router

API_ROUTERS = (
    identity_router,
    uploads_router,
    catalogs_router,
    reference_catalogs_router,
    periods_router,
    indicators_catalog_router,
    evidence_router,
    captures_router,
    validation_router,
    scoring_router,
    reports_router,
    poa_planning_router,
    poa_tracking_router,
    poa_validation_router,
    poa_reports_router,
    dashboards_router,
    notifications_router,
    audit_router,
)


def include_api_routers(app: FastAPI, prefix: str) -> None:
    for router in API_ROUTERS:
        app.include_router(router, prefix=prefix)
