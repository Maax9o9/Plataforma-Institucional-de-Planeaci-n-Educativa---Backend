from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum, auto

from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.poa_planning.domain.ports.repositories import PoaRepository
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError, ValidationError

from ...domain.entities import (
    EL_AREA_NO_EXISTE,
    EL_EJERCICIO_POA_NO_EXISTE,
    LA_ACTIVIDAD_LA_MOVIERON,
    Activity,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    ensure_can_be_submitted,
    ensure_is_still_a_draft,
    ensure_node_can_be_chosen,
)
from ...domain.ports.area_leadership import AreaLeadership
from ...domain.ports.repositories import PoaAreaRepository


class LoQueNoSeMando(Enum):
    SIN_CAMBIO = auto()


SIN_CAMBIO = LoQueNoSeMando.SIN_CAMBIO

CAMPOS_QUE_EL_GUARDADO_PARCIAL_PUEDE_OMITIR = (
    "name",
    "node_id",
    "unit_id",
    "evaluation_method",
    "annual_target",
    "monthly",
    "is_active",
)


@dataclass(kw_only=True)
class OpenPoaAreaCommand:
    exercise_id: int
    area_id: int


@dataclass(kw_only=True)
class SaveActivityCommand:
    poa_area_id: int
    activity_id: int | None = None
    version: int | None = None
    name: str | LoQueNoSeMando = SIN_CAMBIO
    node_id: int | None | LoQueNoSeMando = SIN_CAMBIO
    unit_id: int | None | LoQueNoSeMando = SIN_CAMBIO
    evaluation_method: str | None | LoQueNoSeMando = SIN_CAMBIO
    annual_target: Decimal | None | LoQueNoSeMando = SIN_CAMBIO
    monthly: list[MonthlyTarget] | LoQueNoSeMando = SIN_CAMBIO
    is_active: bool | LoQueNoSeMando = SIN_CAMBIO


@dataclass(kw_only=True)
class SubmitPoaAreaCommand:
    poa_area_id: int
    version: int


class OpenPoaArea:
    def __init__(
        self,
        poa_areas: PoaAreaRepository,
        exercises: PoaRepository,
        areas: AreaRepository,
    ) -> None:
        self.poa_areas = poa_areas
        self.exercises = exercises
        self.areas = areas

    async def execute(self, cmd: OpenPoaAreaCommand) -> PoaArea:
        existente = await self.poa_areas.find_poa_area(cmd.exercise_id, cmd.area_id)
        if existente is not None:
            return existente
        if await self.exercises.get_exercise(cmd.exercise_id) is None:
            raise ValidationError(EL_EJERCICIO_POA_NO_EXISTE)
        if await self.areas.get_by_id(cmd.area_id) is None:
            raise ValidationError(EL_AREA_NO_EXISTE)
        abierto = PoaArea(exercise_id=cmd.exercise_id, area_id=cmd.area_id)
        await self.poa_areas.add_poa_area(abierto)
        return abierto


class SavePoaActivity:
    def __init__(self, poa_areas: PoaAreaRepository, tree: StrategicTreeRepository) -> None:
        self.poa_areas = poa_areas
        self.tree = tree

    async def execute(self, cmd: SaveActivityCommand) -> Activity:
        poa_area = await self.poa_areas.get_poa_area(cmd.poa_area_id)
        if poa_area is None:
            raise ResourceNotFoundError("El POA del área no existe.")
        ensure_is_still_a_draft(poa_area)

        guardada = await self._la_que_se_edita(cmd)
        if guardada is not None and not _lo_que_se_mando(cmd):
            if guardada.version != cmd.version:
                raise ConflictError(LA_ACTIVIDAD_LA_MOVIERON)
            return guardada
        actividad = _con_lo_que_se_mando(guardada, cmd)
        if actividad.node_id is not None and (
            guardada is None or actividad.node_id != guardada.node_id
        ):
            ensure_node_can_be_chosen(await self.tree.get_by_id(actividad.node_id))

        if guardada is None:
            await self.poa_areas.add_activity(actividad)
        else:
            await self.poa_areas.update_activity_if_version_matches(actividad)
        return actividad

    async def _la_que_se_edita(self, cmd: SaveActivityCommand) -> Activity | None:
        if cmd.activity_id is None:
            return None
        guardada = await self.poa_areas.get_activity(cmd.activity_id)
        if guardada is None or guardada.poa_area_id != cmd.poa_area_id:
            raise ResourceNotFoundError("La actividad no existe en este POA del área.")
        if cmd.version is None:
            raise ValidationError(
                "Para editar una actividad hay que decir sobre qué versión se edita, o el "
                "cambio de otra persona se perdería sin avisar."
            )
        return guardada


class SubmitPoaArea:
    def __init__(self, poa_areas: PoaAreaRepository, leadership: AreaLeadership) -> None:
        self.poa_areas = poa_areas
        self.leadership = leadership

    async def execute(self, cmd: SubmitPoaAreaCommand) -> PoaArea:
        poa_area = await self.poa_areas.get_poa_area(cmd.poa_area_id)
        if poa_area is None:
            raise ResourceNotFoundError("El POA del área no existe.")
        ensure_is_still_a_draft(poa_area)
        ensure_can_be_submitted(
            await self.poa_areas.list_activities(cmd.poa_area_id, include_inactive=True),
            area_has_person_in_charge=await self.leadership.has_person_in_charge(poa_area.area_id),
        )
        enviado = replace(poa_area, status=PoaAreaStatus.ENVIADO, version=cmd.version)
        await self.poa_areas.save_poa_area_if_version_matches(enviado)
        return enviado


def _lo_que_se_mando(cmd: SaveActivityCommand) -> dict[str, object]:
    return {
        campo: getattr(cmd, campo)
        for campo in CAMPOS_QUE_EL_GUARDADO_PARCIAL_PUEDE_OMITIR
        if getattr(cmd, campo) is not SIN_CAMBIO
    }


def _con_lo_que_se_mando(guardada: Activity | None, cmd: SaveActivityCommand) -> Activity:
    if guardada is None:
        if cmd.name is SIN_CAMBIO:
            raise ValidationError("La denominación de la actividad es obligatoria.")
        partida = Activity(poa_area_id=cmd.poa_area_id, name=cmd.name)
    else:
        partida = replace(guardada, monthly=list(guardada.monthly), version=cmd.version)
    return replace(partida, **_lo_que_se_mando(cmd))
