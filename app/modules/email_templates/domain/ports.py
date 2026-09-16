"""Contratos de catálogo, persistencia y presentación de correos."""

from typing import Protocol

from app.shared.application.ports.email_composer import ComposedEmail

from .entities import TemplateDefinition, TemplateOverride


class TemplateRepository(Protocol):
    async def get(self, key: str) -> TemplateOverride | None: ...
    async def save(
        self,
        key: str,
        content: dict[str, str],
        expected_version: int,
        actor_id: int,
    ) -> TemplateOverride: ...


class TemplateCatalog(Protocol):
    def list(self) -> list[TemplateDefinition]: ...
    def get(self, key: str) -> TemplateDefinition: ...


class EmailRenderer(Protocol):
    def render(
        self,
        definition: TemplateDefinition,
        content: dict[str, str],
        *,
        recipient_name: str,
        detail: str,
        action_url: str | None,
    ) -> ComposedEmail: ...
