"""Composition root de adaptadores, separado de FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.audit.infrastructure.repository import InMemoryAuditRepository
from app.modules.audit.infrastructure.sql_repository import SqlAlchemyAuditRepository
from app.modules.dashboards.application.service import (
    InMemoryDashboardService,
    SqlAlchemyDashboardService,
)
from app.modules.evidence_management.infrastructure.repository import InMemoryEvidenceRepository
from app.modules.evidence_management.infrastructure.sql_repository import (
    SqlAlchemyEvidenceRepository,
)
from app.modules.identity_access.infrastructure.password_setup_store import (
    InMemoryPasswordSetupTokenStore,
    SqlAlchemyPasswordSetupTokenStore,
)
from app.modules.identity_access.infrastructure.refresh_store import InMemoryRefreshTokenStore
from app.modules.identity_access.infrastructure.repository import InMemoryUserRepository
from app.modules.identity_access.infrastructure.sql_repository import (
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserRepository,
)
from app.modules.indicators_capture.infrastructure.repository import InMemoryCaptureRepository
from app.modules.indicators_capture.infrastructure.sql_repository import SqlAlchemyCaptureRepository
from app.modules.indicators_catalog.infrastructure.repository import InMemoryIndicatorRepository
from app.modules.indicators_catalog.infrastructure.sql_repository import (
    SqlAlchemyIndicatorRepository,
)
from app.modules.indicators_reports.application.service import (
    InMemoryIndicatorReportService,
    InMemoryReportLog,
    SqlAlchemyIndicatorReportService,
)
from app.modules.indicators_reports.infrastructure.repository import SqlAlchemyReportLog
from app.modules.indicators_scoring.infrastructure.repository import (
    InMemoryThresholdConfigRepository,
)
from app.modules.indicators_scoring.infrastructure.sql_repository import (
    SqlAlchemyThresholdConfigRepository,
)
from app.modules.indicators_validation.infrastructure.repository import (
    InMemoryStateChangeRepository,
)
from app.modules.indicators_validation.infrastructure.sql_repository import (
    SqlAlchemyStateChangeRepository,
)
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
from app.modules.notifications.infrastructure.repository import InMemoryNotificationRepository
from app.modules.notifications.infrastructure.sql_repository import SqlAlchemyNotificationRepository
from app.modules.periods.infrastructure.repository import InMemoryPeriodRepository
from app.modules.periods.infrastructure.sql_repository import SqlAlchemyPeriodRepository
from app.modules.poa_planning.infrastructure.repository import InMemoryPoaRepository
from app.modules.poa_planning.infrastructure.sql_repository import SqlAlchemyPoaRepository
from app.modules.poa_reports.application.service import (
    InMemoryPoaReportService,
    SqlAlchemyPoaReportService,
)
from app.modules.poa_tracking.infrastructure.repository import InMemoryPoaAdvanceRepository
from app.modules.poa_tracking.infrastructure.sql_repository import SqlAlchemyPoaAdvanceRepository
from app.shared.infrastructure.db.session import create_database


@dataclass
class Resources:
    db_engine: object | None
    db_session_factory: object | None
    user_repository: object
    refresh_token_store: object
    area_repository: object
    instrument_repository: object
    period_repository: object
    audit_repository: object
    indicator_repository: object
    evidence_repository: object
    capture_repository: object
    criteria_repository: object
    indicator_type_repository: object
    state_change_repository: object
    threshold_config_repository: object
    poa_repository: object
    poa_advance_repository: object
    poa_report_service: object
    dashboard_service: object
    indicator_report_service: object
    report_log: object
    notification_repository: object
    password_setup_token_store: object


def create_resources(settings: Settings) -> Resources:
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
        criteria_repository = SqlAlchemyReferenceRepository(db_session_factory, CriteriaSeaesModel)
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

    return Resources(
        db_engine=db_engine,
        db_session_factory=db_session_factory,
        user_repository=user_repository,
        refresh_token_store=refresh_token_store,
        area_repository=area_repository,
        instrument_repository=instrument_repository,
        period_repository=period_repository,
        audit_repository=audit_repository,
        indicator_repository=indicator_repository,
        evidence_repository=evidence_repository,
        capture_repository=capture_repository,
        criteria_repository=criteria_repository,
        indicator_type_repository=indicator_type_repository,
        state_change_repository=state_change_repository,
        threshold_config_repository=threshold_config_repository,
        poa_repository=poa_repository,
        poa_advance_repository=poa_advance_repository,
        poa_report_service=poa_report_service,
        dashboard_service=dashboard_service,
        indicator_report_service=indicator_report_service,
        report_log=report_log,
        notification_repository=notification_repository,
        password_setup_token_store=password_setup_token_store,
    )
