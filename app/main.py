from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.cors import build_cors_options
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.core.openapi import custom_openapi
from app.modules.audit.api.router import router as audit_router
from app.modules.audit.infrastructure.repository import InMemoryAuditRepository
from app.modules.audit.infrastructure.sql_repository import SqlAlchemyAuditRepository
from app.modules.audit.infrastructure.subscriber import register_audit_subscriber
from app.modules.dashboards.api.router import router as dashboards_router
from app.modules.dashboards.application.service import (
    InMemoryDashboardService,
    SqlAlchemyDashboardService,
)
from app.modules.evidence_management.api.router import router as evidence_router
from app.modules.evidence_management.infrastructure.repository import InMemoryEvidenceRepository
from app.modules.evidence_management.infrastructure.sql_repository import (
    SqlAlchemyEvidenceRepository,
)
from app.modules.identity_access.api.router import router as identity_router
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.password_setup_store import (
    InMemoryPasswordSetupTokenStore,
    SqlAlchemyPasswordSetupTokenStore,
)
from app.modules.identity_access.infrastructure.refresh_store import InMemoryRefreshTokenStore
from app.modules.identity_access.infrastructure.repository import InMemoryUserRepository
from app.modules.identity_access.infrastructure.revoked_token_store import InMemoryRevokedTokenStore
from app.modules.identity_access.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenService,
)
from app.modules.identity_access.infrastructure.sql_repository import (
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserRepository,
)
from app.modules.indicators_capture.api.router import router as captures_router
from app.modules.indicators_capture.domain.events import CaptureCreated, CaptureSent
from app.modules.indicators_capture.domain.value_objects import CaptureStatus
from app.modules.indicators_capture.infrastructure.repository import InMemoryCaptureRepository
from app.modules.indicators_capture.infrastructure.sql_repository import SqlAlchemyCaptureRepository
from app.modules.indicators_catalog.api.router import router as indicators_catalog_router
from app.modules.indicators_catalog.infrastructure.repository import InMemoryIndicatorRepository
from app.modules.indicators_catalog.infrastructure.sql_repository import (
    SqlAlchemyIndicatorRepository,
)
from app.modules.indicators_reports.api.router import router as reports_router
from app.modules.indicators_reports.application.service import (
    InMemoryIndicatorReportService,
    InMemoryReportLog,
    SqlAlchemyIndicatorReportService,
)
from app.modules.indicators_reports.infrastructure.repository import SqlAlchemyReportLog
from app.modules.indicators_scoring.api.router import router as scoring_router
from app.modules.indicators_scoring.application.dto import CalculateEvaluationCommand
from app.modules.indicators_scoring.application.use_cases.calculate_evaluation import (
    CalculateEvaluation,
)
from app.modules.indicators_scoring.infrastructure.repository import (
    InMemoryThresholdConfigRepository,
)
from app.modules.indicators_scoring.infrastructure.sql_repository import (
    SqlAlchemyThresholdConfigRepository,
)
from app.modules.indicators_validation.api.router import router as validation_router
from app.modules.indicators_validation.domain.entities import StateChange
from app.modules.indicators_validation.domain.events import CaptureValidated
from app.modules.indicators_validation.infrastructure.repository import (
    InMemoryStateChangeRepository,
)
from app.modules.indicators_validation.infrastructure.sql_repository import (
    SqlAlchemyStateChangeRepository,
)
from app.modules.institutional_catalogs.api.reference_router import (
    router as reference_catalogs_router,
)
from app.modules.institutional_catalogs.api.router import router as catalogs_router
from app.modules.institutional_catalogs.infrastructure.models import (
    CriteriaSeaesModel,
    IndicatorTypeModel,
)
from app.modules.institutional_catalogs.infrastructure.reference_repository import (
    InMemoryReferenceRepository,
)
from app.modules.institutional_catalogs.infrastructure.reference_sql_repository import (
    SqlAlchemyReferenceRepository,
)
from app.modules.institutional_catalogs.infrastructure.repository import (
    InMemoryAreaRepository,
    InMemoryInstrumentRepository,
)
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyAreaRepository,
    SqlAlchemyInstrumentRepository,
)
from app.modules.notifications.api.router import router as notifications_router
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.infrastructure.repository import InMemoryNotificationRepository
from app.modules.notifications.infrastructure.sql_repository import SqlAlchemyNotificationRepository
from app.modules.periods.api.router import router as periods_router
from app.modules.periods.infrastructure.repository import InMemoryPeriodRepository
from app.modules.periods.infrastructure.sql_repository import SqlAlchemyPeriodRepository
from app.modules.poa_planning.api.router import router as poa_planning_router
from app.modules.poa_planning.infrastructure.repository import InMemoryPoaRepository
from app.modules.poa_planning.infrastructure.sql_repository import SqlAlchemyPoaRepository
from app.modules.poa_reports.api.router import router as poa_reports_router
from app.modules.poa_reports.application.service import (
    InMemoryPoaReportService,
    SqlAlchemyPoaReportService,
)
from app.modules.poa_tracking.api.router import router as poa_tracking_router
from app.modules.poa_tracking.infrastructure.repository import InMemoryPoaAdvanceRepository
from app.modules.poa_tracking.infrastructure.sql_repository import SqlAlchemyPoaAdvanceRepository
from app.modules.poa_validation.api.router import router as poa_validation_router
from app.shared.infrastructure.db.session import create_database
from app.shared.infrastructure.email.factory import create_email_sender
from app.shared.infrastructure.events.in_memory_event_bus import InMemoryEventBus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        if await app.state.user_repository.get_by_email(settings.bootstrap_admin_email) is None:
            await CreateUser(
                repository=app.state.user_repository,
                password_hasher=app.state.password_hasher,
                event_bus=app.state.event_bus,
            ).execute(
                RegisterUserCommand(
                    email=settings.bootstrap_admin_email,
                    full_name="Administrador inicial",
                    password=settings.bootstrap_admin_password,
                    roles={Role.ADMIN_SISTEMA},
                    area_id=None,
                )
            )
            logger.info("Usuario administrador inicial creado")
    elif settings.environment == "development":
        logger.info("No se configuro usuario bootstrap; la autenticacion inicia sin usuarios")
    try:
        yield
    finally:
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    if settings.secret_key is None:
        if settings.environment == "production":
            raise RuntimeError("SECRET_KEY debe estar configurada en produccion.")
        settings.secret_key = SecretStr(secrets.token_urlsafe(32))
    elif settings.environment == "production" and len(settings.secret_key.get_secret_value()) < 32:
        raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres en produccion.")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "API inicial de la Plataforma Institucional de Planeacion Educativa. "
            "Usa SQLAlchemy async cuando DATABASE_URL esta configurada y memoria "
            "como fallback local."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    event_bus = InMemoryEventBus()
    db_engine, db_session_factory = create_database(settings)
    if db_session_factory is None:
        user_repository = InMemoryUserRepository()
        refresh_token_store = InMemoryRefreshTokenStore()
        area_repository = InMemoryAreaRepository()
        instrument_repository = InMemoryInstrumentRepository()
        period_repository = InMemoryPeriodRepository()
        audit_repository = InMemoryAuditRepository()
        indicator_repository = InMemoryIndicatorRepository()
        evidence_repository = InMemoryEvidenceRepository()
        capture_repository = InMemoryCaptureRepository()
        criteria_repository = InMemoryReferenceRepository()
        indicator_type_repository = InMemoryReferenceRepository()
        state_change_repository = InMemoryStateChangeRepository()
        threshold_config_repository = InMemoryThresholdConfigRepository()
        poa_repository = InMemoryPoaRepository()
        poa_advance_repository = InMemoryPoaAdvanceRepository()
        poa_report_service = InMemoryPoaReportService(poa_repository, poa_advance_repository)
        dashboard_service = InMemoryDashboardService(
            indicator_repository,
            capture_repository,
            poa_repository,
            poa_advance_repository,
        )
        indicator_report_service = InMemoryIndicatorReportService(
            indicator_repository,
            capture_repository,
            instrument_repository,
        )
        report_log = InMemoryReportLog()
        notification_repository = InMemoryNotificationRepository()
        password_setup_token_store = InMemoryPasswordSetupTokenStore()
    else:
        user_repository = SqlAlchemyUserRepository(db_session_factory)
        refresh_token_store = SqlAlchemyRefreshTokenStore(db_session_factory)
        area_repository = SqlAlchemyAreaRepository(db_session_factory)
        instrument_repository = SqlAlchemyInstrumentRepository(db_session_factory)
        period_repository = SqlAlchemyPeriodRepository(db_session_factory)
        audit_repository = SqlAlchemyAuditRepository(db_session_factory)
        indicator_repository = SqlAlchemyIndicatorRepository(db_session_factory)
        evidence_repository = SqlAlchemyEvidenceRepository(db_session_factory)
        capture_repository = SqlAlchemyCaptureRepository(db_session_factory)
        criteria_repository = SqlAlchemyReferenceRepository(
            db_session_factory,
            CriteriaSeaesModel,
        )
        indicator_type_repository = SqlAlchemyReferenceRepository(
            db_session_factory,
            IndicatorTypeModel,
        )
        state_change_repository = SqlAlchemyStateChangeRepository(db_session_factory)
        threshold_config_repository = SqlAlchemyThresholdConfigRepository(db_session_factory)
        poa_repository = SqlAlchemyPoaRepository(db_session_factory)
        poa_advance_repository = SqlAlchemyPoaAdvanceRepository(db_session_factory)
        poa_report_service = SqlAlchemyPoaReportService(db_session_factory)
        dashboard_service = SqlAlchemyDashboardService(db_session_factory)
        indicator_report_service = SqlAlchemyIndicatorReportService(db_session_factory)
        report_log = SqlAlchemyReportLog(db_session_factory)
        notification_repository = SqlAlchemyNotificationRepository(db_session_factory)
        password_setup_token_store = SqlAlchemyPasswordSetupTokenStore(db_session_factory)

    app.state.settings = settings
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    app.state.event_bus = event_bus
    app.state.user_repository = user_repository
    app.state.password_hasher = Argon2PasswordHasher()
    app.state.token_service = JwtTokenService(settings)
    app.state.refresh_token_store = refresh_token_store
    app.state.revoked_token_store = InMemoryRevokedTokenStore()
    app.state.area_repository = area_repository
    app.state.instrument_repository = instrument_repository
    app.state.period_repository = period_repository
    app.state.audit_repository = audit_repository
    app.state.indicator_repository = indicator_repository
    app.state.evidence_repository = evidence_repository
    app.state.capture_repository = capture_repository
    app.state.criteria_repository = criteria_repository
    app.state.indicator_type_repository = indicator_type_repository
    app.state.state_change_repository = state_change_repository
    app.state.threshold_config_repository = threshold_config_repository
    app.state.poa_repository = poa_repository
    app.state.poa_advance_repository = poa_advance_repository
    app.state.poa_report_service = poa_report_service
    app.state.dashboard_service = dashboard_service
    app.state.indicator_report_service = indicator_report_service
    app.state.report_log = report_log
    app.state.notification_repository = notification_repository
    app.state.email_sender = create_email_sender(settings)
    app.state.password_setup_token_store = password_setup_token_store

    register_audit_subscriber(event_bus, audit_repository)
    NotificationService(
        notification_repository,
        user_repository,
        app.state.email_sender,
        indicator_repository,
    ).register(event_bus)

    evaluation = CalculateEvaluation(
        indicators=indicator_repository,
        captures=capture_repository,
        goals=indicator_repository,
        config=threshold_config_repository,
        event_bus=event_bus,
    )

    async def calculate_after_validation(event: CaptureValidated) -> None:
        await evaluation.execute(
            CalculateEvaluationCommand(
                capture_id=int(event.data["capture_id"]),
                indicator_id=int(event.data["indicator_id"]),
                period_id=int(event.data["period_id"]),
            )
        )

    event_bus.subscribe(CaptureValidated, calculate_after_validation)

    async def record_capture_created(event: CaptureCreated) -> None:
        await state_change_repository.add(
            StateChange(
                entity_id=event.aggregate_id,
                from_status=None,
                to_status=CaptureStatus.DRAFT,
                user_id=event.actor_id,
                comment=None,
                created_at=event.occurred_at,
            )
        )

    async def record_capture_sent(event: CaptureSent) -> None:
        await state_change_repository.add(
            StateChange(
                entity_id=event.aggregate_id,
                from_status=CaptureStatus(event.data["from_status"]),
                to_status=CaptureStatus.SENT,
                user_id=event.actor_id,
                comment=None,
                created_at=event.occurred_at,
            )
        )

    event_bus.subscribe(CaptureCreated, record_capture_created)
    event_bus.subscribe(CaptureSent, record_capture_sent)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        **build_cors_options(settings),
    )
    register_exception_handlers(app)

    @app.get("/health", tags=["System"], summary="Verificar disponibilidad de la API")
    async def health() -> dict[str, str]:
        if app.state.db_session_factory is not None:
            try:
                async with app.state.db_session_factory() as session:
                    await session.execute(text("SELECT 1"))
            except SQLAlchemyError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="La base de datos no esta disponible.",
                ) from exc
            return {"status": "ok", "environment": settings.environment, "database": "connected"}
        return {"status": "ok", "environment": settings.environment, "database": "in_memory"}

    app.include_router(identity_router, prefix=settings.api_v1_prefix)
    app.include_router(catalogs_router, prefix=settings.api_v1_prefix)
    app.include_router(reference_catalogs_router, prefix=settings.api_v1_prefix)
    app.include_router(indicators_catalog_router, prefix=settings.api_v1_prefix)
    app.include_router(evidence_router, prefix=settings.api_v1_prefix)
    app.include_router(captures_router, prefix=settings.api_v1_prefix)
    app.include_router(validation_router, prefix=settings.api_v1_prefix)
    app.include_router(scoring_router, prefix=settings.api_v1_prefix)
    app.include_router(reports_router, prefix=settings.api_v1_prefix)
    app.include_router(poa_planning_router, prefix=settings.api_v1_prefix)
    app.include_router(poa_tracking_router, prefix=settings.api_v1_prefix)
    app.include_router(poa_validation_router, prefix=settings.api_v1_prefix)
    app.include_router(poa_reports_router, prefix=settings.api_v1_prefix)
    app.include_router(dashboards_router, prefix=settings.api_v1_prefix)
    app.include_router(notifications_router, prefix=settings.api_v1_prefix)
    app.include_router(periods_router, prefix=settings.api_v1_prefix)
    app.include_router(audit_router, prefix=settings.api_v1_prefix)
    app.openapi = lambda: custom_openapi(app)
    return app


app = create_app()
