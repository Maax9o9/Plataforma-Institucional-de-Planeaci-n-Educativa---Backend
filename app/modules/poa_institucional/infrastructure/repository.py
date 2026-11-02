from __future__ import annotations

from dataclasses import replace
from itertools import count

from app.modules.identity_access.domain.ports.user_repository import UserReader
from app.modules.identity_access.domain.value_objects import Role
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ..domain.entities import (
    EL_AREA_YA_TIENE_SU_POA,
    EL_POA_DEL_AREA_NO_EXISTE,
    EL_POA_DEL_AREA_SE_REABRIO_A_LA_VEZ,
    LA_ACTIVIDAD_LA_MOVIERON,
    LO_MOVIERON_AL_ENVIAR,
    LO_MOVIERON_AL_REABRIR,
    Activity,
    CaptureWindow,
    PoaArea,
)


def _copia(activity: Activity) -> Activity:
    return replace(activity, monthly=[replace(mes) for mes in activity.monthly])


class InMemoryPoaAreaRepository:
    def __init__(self) -> None:
        self._next_poa_area_id = count(1)
        self._next_activity_id = count(1)
        self._next_window_id = count(1)
        self._poa_areas: dict[int, PoaArea] = {}
        self._activities: dict[int, Activity] = {}
        self._windows: dict[int, CaptureWindow] = {}

    async def get_poa_area(self, poa_area_id: int) -> PoaArea | None:
        guardado = self._poa_areas.get(poa_area_id)
        return replace(guardado) if guardado is not None else None

    async def find_poa_area(self, exercise_id: int, area_id: int) -> PoaArea | None:
        for guardado in self._poa_areas.values():
            if guardado.exercise_id == exercise_id and guardado.area_id == area_id:
                return replace(guardado)
        return None

    async def add_poa_area(self, poa_area: PoaArea, window: CaptureWindow) -> None:
        poa_area.validate()
        window.validate()
        if await self.find_poa_area(poa_area.exercise_id, poa_area.area_id) is not None:
            raise ConflictError(EL_AREA_YA_TIENE_SU_POA)
        poa_area.id = next(self._next_poa_area_id)
        self._poa_areas[poa_area.id] = replace(poa_area)
        self._guardar_ventana(poa_area.id, window)

    async def reopen_poa_area(self, poa_area: PoaArea, window: CaptureWindow) -> None:
        window.validate()
        if any(
            guardada.poa_area_id == poa_area.id and guardada.number == window.number
            for guardada in self._windows.values()
        ):
            raise ConflictError(EL_POA_DEL_AREA_SE_REABRIO_A_LA_VEZ)
        self._guardar_si_la_version_coincide(poa_area, LO_MOVIERON_AL_REABRIR)
        self._guardar_ventana(poa_area.id, window)

    def _guardar_si_la_version_coincide(self, poa_area: PoaArea, lo_movieron: str) -> None:
        poa_area.validate()
        guardado = self._poa_areas.get(poa_area.id)
        if guardado is None:
            raise ResourceNotFoundError(EL_POA_DEL_AREA_NO_EXISTE)
        if guardado.version != poa_area.version:
            raise ConflictError(lo_movieron)
        poa_area.version += 1
        self._poa_areas[poa_area.id] = replace(poa_area)

    async def current_capture_window(self, poa_area_id: int) -> CaptureWindow | None:
        historia = await self.capture_windows(poa_area_id)
        return historia[-1] if historia else None

    async def capture_windows(self, poa_area_id: int) -> list[CaptureWindow]:
        return [
            replace(guardada)
            for guardada in sorted(self._windows.values(), key=lambda una: una.number)
            if guardada.poa_area_id == poa_area_id
        ]

    def _guardar_ventana(self, poa_area_id: int, window: CaptureWindow) -> None:
        window.id = next(self._next_window_id)
        window.poa_area_id = poa_area_id
        self._windows[window.id] = replace(window)

    async def save_poa_area_if_version_matches(self, poa_area: PoaArea) -> None:
        self._guardar_si_la_version_coincide(poa_area, LO_MOVIERON_AL_ENVIAR)

    async def list_activities(
        self, poa_area_id: int, *, include_inactive: bool = False
    ) -> list[Activity]:
        return [
            _copia(replace(activity, monthly=activity.months()))
            for activity in sorted(self._activities.values(), key=lambda una: una.id)
            if activity.poa_area_id == poa_area_id and (include_inactive or activity.is_active)
        ]

    async def get_activity(self, activity_id: int) -> Activity | None:
        guardada = self._activities.get(activity_id)
        if guardada is None:
            return None
        return _copia(replace(guardada, monthly=guardada.months()))

    async def add_activity(self, activity: Activity) -> None:
        activity.validate()
        if activity.poa_area_id not in self._poa_areas:
            raise ResourceNotFoundError("El POA del área no existe.")
        activity.id = next(self._next_activity_id)
        activity.version = 1
        self._activities[activity.id] = _copia(activity)

    async def update_activity_if_version_matches(self, activity: Activity) -> None:
        activity.validate()
        guardada = self._activities.get(activity.id)
        if guardada is None:
            raise ResourceNotFoundError("La actividad no existe.")
        if guardada.version != activity.version:
            raise ConflictError(LA_ACTIVIDAD_LA_MOVIERON)
        activity.version += 1
        self._activities[activity.id] = _copia(activity)


class InMemoryAreaLeadership:
    def __init__(self, users: UserReader) -> None:
        self.users = users

    async def has_person_in_charge(self, area_id: int) -> bool:
        return any(
            usuario.area_id == area_id and Role.RESPONSABLE_AREA in usuario.roles
            for usuario in await self.users.list(active_only=True)
        )
