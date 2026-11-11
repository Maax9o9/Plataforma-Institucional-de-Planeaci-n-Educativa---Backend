"""Casos de uso del catalogo de unidades de medida de las actividades del POA.

La unidad de medida se ofrece, no se impone: la actividad sigue guardando su
unidad como texto libre. Estos casos de uso solo gobiernan el catalogo de
sugerencias (crear, editar, desactivar), no la escritura de la actividad.
"""

from __future__ import annotations

from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ...domain.ports.repositories import UnitOfMeasureRepository
from ...domain.unit_of_measure_entities import UnitOfMeasure


class CreateUnitOfMeasure:
    def __init__(self, repository: UnitOfMeasureRepository) -> None:
        self.repository = repository

    async def execute(self, *, key: str, name: str, plural: str) -> UnitOfMeasure:
        item = UnitOfMeasure.create(key=key, name=name, plural=plural)
        await self.repository.add(item)
        return item


def _check_version(item: UnitOfMeasure, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != item.version:
        raise ConflictError(
            "La unidad de medida fue modificada por otra solicitud.",
            details={"version_actual": item.version},
        )


class UpdateUnitOfMeasure:
    def __init__(self, repository: UnitOfMeasureRepository) -> None:
        self.repository = repository

    async def execute(
        self,
        item_id: int,
        *,
        key: str | None,
        name: str | None,
        plural: str | None,
        expected_version: int | None = None,
    ) -> UnitOfMeasure:
        item = await self.repository.get_by_id(item_id)
        if item is None:
            raise ResourceNotFoundError("La unidad de medida no existe.")
        _check_version(item, expected_version)
        item.update_details(key=key, name=name, plural=plural)
        await self.repository.update(item)
        return item


class DeactivateUnitOfMeasure:
    def __init__(self, repository: UnitOfMeasureRepository) -> None:
        self.repository = repository

    async def execute(self, item_id: int, expected_version: int | None = None) -> UnitOfMeasure:
        item = await self.repository.get_by_id(item_id)
        if item is None:
            raise ResourceNotFoundError("La unidad de medida no existe.")
        _check_version(item, expected_version)
        item.deactivate()
        await self.repository.update(item)
        return item
