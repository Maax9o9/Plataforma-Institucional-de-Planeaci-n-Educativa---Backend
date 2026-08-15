"""Persistencia del registro de reportes generados."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..application.service import ReportResult
from .models import ReportLogModel


class SqlAlchemyReportLog:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def record(self, report: ReportResult, user_id: int, format_: str) -> None:
        async with self.session_factory() as session:
            session.add(
                ReportLogModel(
                    usuario_id=user_id,
                    tipo=report.report_type,
                    parametros=report.filters,
                    formato=format_,
                    generado_en=datetime.now(UTC),
                )
            )
            await session.commit()
