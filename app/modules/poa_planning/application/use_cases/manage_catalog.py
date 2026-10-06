"""Administración del catálogo del PSE: objetivos, estrategias, indicadores y acciones."""

from __future__ import annotations

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError, ValidationError

from ...domain.cedula_entities import (
    PoaActivityCatalog,
    PoaIndicatorCatalog,
    PoaObjectiveCatalog,
    PoaStrategyCatalog,
)
from ...domain.ports.cedula_repository import PoaFormRepository
from ..access_control import ensure_planning


class PoaCatalogAdmin:
    """Alta, edición y baja lógica del catálogo del PSE.

    **No hay borrado, y es una decisión.** Las cédulas apuntan al catálogo por
    llave foránea: borrar una estrategia que ya se usó rompería el POA donde se
    usó, o lo dejaría sin denominación. Lo que existe es `activo`, que gobierna
    si se puede *elegir de nuevo* —no lo que ya se eligió—. Un POA formulado y
    aprobado conserva su estrategia aunque el catálogo la retire: la fila sigue
    ahí y sigue resolviendo su nombre.

    Por eso los listados tienen dos lecturas: los selectores piden sólo lo
    activo, y esta pantalla pide todo para poder volver a habilitarlo.
    """

    def __init__(self, repository: PoaFormRepository) -> None:
        self.repository = repository

    async def save_objective(
        self, *, number: int, key: str, denomination: str, is_active: bool,
        actor: ActorContext, creating: bool,
    ) -> PoaObjectiveCatalog:
        ensure_planning(actor)
        _texto("la denominación", denomination)
        existente = await self.repository.get_objective(number)
        _verificar_existencia("El objetivo", existente, creating)
        return await self.repository.save_objective(
            PoaObjectiveCatalog(
                key=key.strip(),
                number=number,
                denomination=denomination.strip(),
                is_active=is_active,
            )
        )

    async def save_strategy(
        self, *, key: str, objective_number: int, denomination: str, is_active: bool,
        actor: ActorContext, creating: bool,
    ) -> PoaStrategyCatalog:
        ensure_planning(actor)
        _texto("la denominación", denomination)
        existente = await self.repository.get_strategy(key)
        _verificar_existencia("La estrategia", existente, creating)
        # El objetivo tiene que existir. La llave foránea también lo exige, pero
        # su error no dice cuál de los dos datos está mal.
        if await self.repository.get_objective(objective_number) is None:
            raise ValidationError(f"El objetivo {objective_number} no existe en el catálogo.")
        return await self.repository.save_strategy(
            PoaStrategyCatalog(
                key=key.strip(),
                objective_number=objective_number,
                denomination=denomination.strip(),
                is_active=is_active,
            )
        )

    async def save_indicator(
        self, *, key: str, objective_number: int, name: str, formula: str, unit: str,
        is_active: bool, actor: ActorContext, creating: bool,
    ) -> PoaIndicatorCatalog:
        ensure_planning(actor)
        _texto("el nombre", name)
        _texto("la fórmula", formula)
        _texto("la unidad de medida", unit)
        existente = await self.repository.get_indicator(key)
        _verificar_existencia("El indicador", existente, creating)
        if await self.repository.get_objective(objective_number) is None:
            raise ValidationError(f"El objetivo {objective_number} no existe en el catálogo.")
        return await self.repository.save_indicator(
            PoaIndicatorCatalog(
                key=key.strip(),
                objective_number=objective_number,
                name=name.strip(),
                formula=formula.strip(),
                unit=unit.strip(),
                is_active=is_active,
            )
        )

    async def save_activity(
        self, *, key: str, strategy_key: str, description: str, is_active: bool,
        actor: ActorContext, creating: bool,
    ) -> PoaActivityCatalog:
        ensure_planning(actor)
        _texto("la descripción", description)
        existente = await self.repository.get_activity_catalog(key)
        _verificar_existencia("La acción", existente, creating)
        if await self.repository.get_strategy(strategy_key) is None:
            raise ValidationError(f"La estrategia {strategy_key} no existe en el catálogo.")
        return await self.repository.save_activity_catalog(
            PoaActivityCatalog(
                key=key.strip(),
                strategy_key=strategy_key.strip(),
                description=description.strip(),
                is_active=is_active,
            )
        )


def _texto(cual: str, valor: str) -> None:
    if not valor.strip():
        raise ValidationError(f"Captura {cual}.")


def _verificar_existencia(que: str, existente: object | None, creating: bool) -> None:
    """Crear algo que ya existe es un conflicto; editar algo que no existe, un
    404. Separarlo evita que un alta pise en silencio una entrada del catálogo
    que alguien más acababa de crear."""
    if creating and existente is not None:
        raise ConflictError(f"{que} ya existe en el catálogo.")
    if not creating and existente is None:
        raise ResourceNotFoundError(f"{que} no existe en el catálogo.")
