"""Administración versionada y composición común de todos los correos."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ..domain.entities import validate_content
from ..domain.ports import EmailRenderer, TemplateCatalog, TemplateRepository


class EmailTemplateService:
    def __init__(
        self,
        repository: TemplateRepository,
        catalog: TemplateCatalog,
        renderer: EmailRenderer,
        event_bus: EventBus,
        unit_of_work,
    ):
        self.repository = repository
        self.catalog = catalog
        self.renderer = renderer
        self.event_bus = event_bus
        self.unit_of_work = unit_of_work

    async def get(self, key: str) -> dict:
        definition = self.catalog.get(key)
        saved = await self.repository.get(key)
        return {
            "tipo": key,
            "etiqueta": definition.label,
            "contenido": {**definition.content, **(saved.content if saved else {})},
            "predeterminado": definition.content,
            "personalizada": bool(saved and saved.content),
            "version": saved.version if saved else 0,
            "actualizado_por": saved.updated_by if saved else None,
            "actualizado_en": saved.updated_at if saved else None,
            "variables": ["nombre"],
        }

    async def list(self) -> list[dict]:
        return [await self.get(item.key) for item in self.catalog.list()]

    async def update(self, key, changes, expected_version, actor_id, *, reset=False):
        self.catalog.get(key)
        if not reset and not changes:
            raise ValidationError("Indique al menos un texto para actualizar.")
        clean = validate_content(changes)
        async with self.unit_of_work():
            saved = await self.repository.get(key)
            content = {} if reset else {**(saved.content if saved else {}), **clean}
            await self.repository.save(key, content, expected_version, actor_id)
            await self.event_bus.publish(
                DomainEvent(
                    actor_id=actor_id,
                    aggregate_type="email_template",
                    action="reset" if reset else "updated",
                    data={"tipo": key, "campos": sorted(clean), "version": expected_version + 1},
                )
            )
        return await self.get(key)

    async def render(
        self,
        key,
        *,
        recipient_name,
        detail,
        action_url=None,
        overrides=None,
    ):
        try:
            definition = self.catalog.get(key)
        except ResourceNotFoundError:
            key = "notificacion_general"
            definition = self.catalog.get(key)
        effective = await self.get(key)
        content = {**effective["contenido"], **validate_content(overrides or {})}
        return self.renderer.render(
            definition,
            content,
            recipient_name=recipient_name,
            detail=detail,
            action_url=action_url,
        )
