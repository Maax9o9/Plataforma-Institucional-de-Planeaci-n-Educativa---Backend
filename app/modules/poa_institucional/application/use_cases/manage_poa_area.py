from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from enum import Enum, auto

from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.poa_planning.domain.ports.repositories import PoaRepository
from app.shared.domain.calendar import institutional_today
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError, ValidationError

from ...domain.entities import (
    EL_AREA_NO_EXISTE,
    EL_EJERCICIO_POA_NO_EXISTE,
    LA_ACTIVIDAD_LA_MOVIERON,
    Activity,
    CaptureWindow,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    el_programa_del_area_sin_abrir,
    ensure_can_be_submitted,
    ensure_capture_is_open,
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


ELIJA_AL_MENOS_UN_AREA = (
    "Elija al menos un área para abrir su Programa Operativo Anual, o ábralo para todas las áreas."
)

NO_HAY_NINGUNA_AREA_ACTIVA = (
    "No hay ninguna área en servicio a la que abrirle su Programa Operativo Anual. Revise el "
    "catálogo de áreas antes de continuar."
)


@dataclass(kw_only=True)
class OpenInstitutionalPoaCommand:
    exercise_id: int
    area_ids: list[int] | None
    opens_on: date
    closes_on: date
    opened_by: int | None = None


@dataclass(kw_only=True)
class ReopenPoaAreaCommand:
    exercise_id: int
    area_id: int
    opens_on: date
    closes_on: date
    reason: str
    opened_by: int | None = None


@dataclass(kw_only=True)
class PoaAreaWithWindow:
    poa_area: PoaArea
    window: CaptureWindow | None = None


@dataclass(kw_only=True)
class OpenedPoa:
    opened: list[PoaAreaWithWindow] = field(default_factory=list)
    already_open: list[PoaAreaWithWindow] = field(default_factory=list)


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


class OpenInstitutionalPoa:
    def __init__(
        self,
        poa_areas: PoaAreaRepository,
        exercises: PoaRepository,
        areas: AreaRepository,
    ) -> None:
        self.poa_areas = poa_areas
        self.exercises = exercises
        self.areas = areas

    async def execute(self, cmd: OpenInstitutionalPoaCommand) -> OpenedPoa:
        self._ventana_de(cmd, 1).validate()
        if await self.exercises.get_exercise(cmd.exercise_id) is None:
            raise ValidationError(EL_EJERCICIO_POA_NO_EXISTE)
        reparto = OpenedPoa()
        for area_id in await self._las_areas_elegidas(cmd):
            abierto = await self._abrir_una(cmd, area_id)
            if abierto is None:
                continue
            (reparto.opened if abierto[1] else reparto.already_open).append(abierto[0])
        return reparto

    async def _abrir_una(
        self, cmd: OpenInstitutionalPoaCommand, area_id: int
    ) -> tuple[PoaAreaWithWindow, bool] | None:
        existente = await self.poa_areas.find_poa_area(cmd.exercise_id, area_id)
        if existente is None:
            abierto = PoaArea(exercise_id=cmd.exercise_id, area_id=area_id)
            ventana = self._ventana_de(cmd, 1)
            try:
                await self.poa_areas.add_poa_area(abierto, ventana)
            except ConflictError:
                existente = await self.poa_areas.find_poa_area(cmd.exercise_id, area_id)
            else:
                return PoaAreaWithWindow(poa_area=abierto, window=ventana), True
        if existente is None:
            return None
        return (
            PoaAreaWithWindow(
                poa_area=existente,
                window=await self.poa_areas.current_capture_window(existente.id),
            ),
            False,
        )

    async def _las_areas_elegidas(self, cmd: OpenInstitutionalPoaCommand) -> list[int]:
        if cmd.area_ids is None:
            activas = sorted(area.id for area in await self.areas.list(active_only=True))
            if not activas:
                raise ValidationError(NO_HAY_NINGUNA_AREA_ACTIVA)
            return activas
        elegidas = sorted(set(cmd.area_ids))
        if not elegidas:
            raise ValidationError(ELIJA_AL_MENOS_UN_AREA)
        for area_id in elegidas:
            area = await self.areas.get_by_id(area_id)
            if area is None:
                raise ValidationError(EL_AREA_NO_EXISTE)
            if not area.is_active:
                raise ValidationError(
                    f"El área de {area.name} está retirada del servicio y no formula su "
                    "Programa Operativo Anual. Quítela de la lista o vuelva a darla de alta "
                    "antes de continuar."
                )
        return elegidas

    @staticmethod
    def _ventana_de(cmd: OpenInstitutionalPoaCommand, numero: int) -> CaptureWindow:
        return CaptureWindow(
            number=numero,
            opens_on=cmd.opens_on,
            closes_on=cmd.closes_on,
            opened_by=cmd.opened_by,
        )


class ReopenPoaArea:
    def __init__(self, poa_areas: PoaAreaRepository, areas: AreaRepository) -> None:
        self.poa_areas = poa_areas
        self.areas = areas

    async def execute(self, cmd: ReopenPoaAreaCommand) -> PoaAreaWithWindow:
        poa_area = await self.poa_areas.find_poa_area(cmd.exercise_id, cmd.area_id)
        if poa_area is None:
            area = await self.areas.get_by_id(cmd.area_id)
            raise ResourceNotFoundError(
                el_programa_del_area_sin_abrir(area.name if area is not None else None)
            )
        vigente = await self.poa_areas.current_capture_window(poa_area.id)
        ventana = CaptureWindow(
            poa_area_id=poa_area.id,
            number=2 if vigente is None else vigente.number + 1,
            opens_on=cmd.opens_on,
            closes_on=cmd.closes_on,
            reason=cmd.reason,
            opened_by=cmd.opened_by,
        )
        ventana.validate()
        reabierto = replace(poa_area, status=PoaAreaStatus.BORRADOR)
        await self.poa_areas.reopen_poa_area(reabierto, ventana)
        return PoaAreaWithWindow(poa_area=reabierto, window=ventana)


async def _exigir_que_el_poa_siga_abierto(
    poa_areas: PoaAreaRepository, areas: AreaRepository, poa_area: PoaArea, today: date
) -> None:
    area = await areas.get_by_id(poa_area.area_id)
    ensure_capture_is_open(
        await poa_areas.current_capture_window(poa_area.id),
        area_name=area.name if area is not None else None,
        today=today,
    )


class SavePoaActivity:
    def __init__(
        self,
        poa_areas: PoaAreaRepository,
        tree: StrategicTreeRepository,
        areas: AreaRepository,
        today: Callable[[], date] = institutional_today,
    ) -> None:
        self.poa_areas = poa_areas
        self.tree = tree
        self.areas = areas
        self.today = today

    async def execute(self, cmd: SaveActivityCommand) -> Activity:
        poa_area = await self.poa_areas.get_poa_area(cmd.poa_area_id)
        if poa_area is None:
            raise ResourceNotFoundError("El POA del área no existe.")
        await _exigir_que_el_poa_siga_abierto(self.poa_areas, self.areas, poa_area, self.today())
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
    def __init__(
        self,
        poa_areas: PoaAreaRepository,
        leadership: AreaLeadership,
        areas: AreaRepository,
        today: Callable[[], date] = institutional_today,
    ) -> None:
        self.poa_areas = poa_areas
        self.leadership = leadership
        self.areas = areas
        self.today = today

    async def execute(self, cmd: SubmitPoaAreaCommand) -> PoaArea:
        poa_area = await self.poa_areas.get_poa_area(cmd.poa_area_id)
        if poa_area is None:
            raise ResourceNotFoundError("El POA del área no existe.")
        await _exigir_que_el_poa_siga_abierto(self.poa_areas, self.areas, poa_area, self.today())
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
