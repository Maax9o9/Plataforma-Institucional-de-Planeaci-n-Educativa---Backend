"""Alta y consulta de los POA: el marco del que cuelga cada año."""

from __future__ import annotations

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ConflictError

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
