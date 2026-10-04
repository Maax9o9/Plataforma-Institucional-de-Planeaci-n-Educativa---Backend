"""Adaptador local con la misma semántica de versión que PostgreSQL."""

from copy import deepcopy
from datetime import UTC, datetime

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import TemplateOverride


def version_conflict():
    return ConflictError(
        "Otra persona modificó esta plantilla. Recárguela antes de guardar.",
        details={"reason": "EMAIL_TEMPLATE_VERSION_CONFLICT", "field": "version"},
    )


class InMemoryTemplateRepository:
    def __init__(self):
        self.items = {}

    async def get(self, key):
        return deepcopy(self.items.get(key))

    async def save(self, key, content, expected_version, actor_id):
        current = self.items.get(key)
        if (current.version if current else 0) != expected_version:
            raise version_conflict()
        result = TemplateOverride(
            key, deepcopy(content), expected_version + 1, actor_id, datetime.now(UTC)
        )
        self.items[key] = result
        return deepcopy(result)
