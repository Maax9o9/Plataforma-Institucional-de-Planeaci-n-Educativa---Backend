"""Alta y consulta de los POA: el marco del que cuelga cada año."""

from __future__ import annotations

from dataclasses import replace

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ...domain.cedula_entities import PoaCatalogo
from ...domain.ports.cedula_repository import PoaFormRepository
from ..access_control import ensure_planning


class ListarCatalogosPoa:
    def __init__(self, repository: PoaFormRepository) -> None:
        self.repository = repository

    async def execute(self, actor: ActorContext) -> list[PoaCatalogo]:
        # Leer no se restringe: el selector de POA lo necesita cualquiera que
        # formule o consulte, y el contenido ya está protegido donde importa.
        return await self.repository.list_catalogs()


class CrearCatalogoPoa:
    """Crea un POA vacío, que luego se llena con el CRUD.

    Es el camino lento y existe desde el primer día: cualquier POA se puede
    construir sin depender de que un archivo venga bien formado.
    """

    def __init__(self, repository: PoaFormRepository) -> None:
        self.repository = repository

    async def execute(
        self, *, name: str, year: int, origin: str | None, actor: ActorContext
    ) -> PoaCatalogo:
        ensure_planning(actor)
        # El camino normal. Dos altas simultáneas se cuelan las dos por aquí:
        # ésas las frena `save_catalog`, que traduce la única del nombre al
        # mismo conflicto.
        if await self.repository.get_catalog_by_name(name.strip()) is not None:
            raise ConflictError(f"Ya existe un POA llamado «{name.strip()}».")
        return await self.repository.save_catalog(
            PoaCatalogo.create(name=name, year=year, origin=origin, created_by=actor.id)
        )


class DuplicarCatalogoPoa:
    def __init__(self, repository: PoaFormRepository) -> None:
        self.repository = repository

    async def execute(
        self, *, origen_id: int, name: str, year: int, actor: ActorContext
    ) -> PoaCatalogo:
        ensure_planning(actor)
        origen = await self.repository.get_catalog(origen_id)
        if origen is None:
            raise ResourceNotFoundError("El POA que se quiere duplicar no existe.")
        copia = await self.repository.save_catalog(
            PoaCatalogo.create(name=name, year=year, origin=origen.origin, created_by=actor.id)
        )

        for objetivo in await self.repository.list_objectives(catalog_id=origen_id):
            await self.repository.save_objective(replace(objetivo, catalog_id=copia.id))
        for estrategia in await self.repository.list_strategies(catalog_id=origen_id):
            await self.repository.save_strategy(replace(estrategia, catalog_id=copia.id))
        for indicador in await self.repository.list_indicators(catalog_id=origen_id):
            await self.repository.save_indicator(replace(indicador, catalog_id=copia.id))
        for actividad in await self.repository.list_activity_catalog(catalog_id=origen_id):
            await self.repository.save_activity_catalog(replace(actividad, catalog_id=copia.id))

        return copia
