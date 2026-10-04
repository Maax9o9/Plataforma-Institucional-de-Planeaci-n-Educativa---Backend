"""Registro único y ordenado de routers HTTP."""

from fastapi import FastAPI

from app.api.uploads_router import router as uploads_router
from app.modules.audit.api.router import router as audit_router
from app.modules.dashboards.api.router import router as dashboards_router
from app.modules.email_templates.api.router import router as email_templates_router
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
from app.modules.poa_planning.api.cedula_router import router as poa_cedula_router
from app.modules.poa_planning.api.router import router as poa_planning_router
from app.modules.poa_reports.api.router import router as poa_reports_router

#: Routers que siempre se registran: identidad, catalogos institucionales,
#: periodos, evidencias, POA, notificaciones, plantillas de correo y bitacora.
CORE_ROUTERS = (
    identity_router,
    uploads_router,
    catalogs_router,
    reference_catalogs_router,
    periods_router,
    evidence_router,
    poa_planning_router,
    poa_cedula_router,
    poa_reports_router,
    notifications_router,
    email_templates_router,
    audit_router,
)

#: Routers del modulo de indicadores del PIDE. Duermen mientras el trabajo se
#: concentra en el POA. Los modulos NO se borran: el POA importa de ellos
#: (CaptureStatus, StateChange y los exportadores de reportes), asi que lo unico
#: que se apaga es su superficie HTTP.
INDICATORS_ROUTERS = (
    indicators_catalog_router,
    captures_router,
    validation_router,
    scoring_router,
    reports_router,
    dashboards_router,
)

#: Se conserva por compatibilidad con lo que ya importaba el registro completo.
API_ROUTERS = CORE_ROUTERS + INDICATORS_ROUTERS


def include_api_routers(app: FastAPI, prefix: str, *, incluir_indicadores: bool = False) -> None:
    routers = CORE_ROUTERS + (INDICATORS_ROUTERS if incluir_indicadores else ())
    for router in routers:
        app.include_router(router, prefix=prefix)
