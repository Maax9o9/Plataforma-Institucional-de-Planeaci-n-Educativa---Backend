"""Actualización optimista atómica, incluyendo la primera personalización."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import TemplateOverride
from .models import EmailTemplateModel
from .repository import version_conflict


class SqlAlchemyTemplateRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    @staticmethod
    def _domain(item):
        return TemplateOverride(
            item.tipo, item.contenido, item.version, item.actualizado_por, item.actualizado_en
        )

    async def get(self, key):
        async with session_scope(self.session_factory) as session:
            model = await session.get(EmailTemplateModel, key)
            return self._domain(model) if model else None

    async def save(self, key, content, expected_version, actor_id):
        values = dict(
            contenido=content,
            version=expected_version + 1,
            actualizado_por=actor_id,
            actualizado_en=datetime.now(UTC),
        )
        if expected_version == 0:
            statement = (
                insert(EmailTemplateModel).values(tipo=key, **values).on_conflict_do_nothing()
            )
        else:
            statement = (
                update(EmailTemplateModel)
                .where(
                    EmailTemplateModel.tipo == key, EmailTemplateModel.version == expected_version
                )
                .values(**values)
            )
        async with session_scope(self.session_factory) as session:
            result = await session.scalar(statement.returning(EmailTemplateModel))
            if result is None:
                raise version_conflict()
            domain = self._domain(result)
            await commit_or_flush(session)
            return domain
