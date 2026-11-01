from __future__ import annotations

from typing import NoReturn

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.models import UserModel, UserRoleModel
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.shared.infrastructure.db.constraints import viola_la_restriccion
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import (
    Activity,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    cabe_en_el_entero_de_la_base,
)
from .models import MonthlyScheduleModel, PoaActivityModel, PoaAreaModel

_UNICO_POA_DEL_AREA_POR_EJERCICIO = "uq_poa_inst_area_ejercicio_area"
_FORANEA_DEL_EJERCICIO = "fk_poa_inst_area_ejercicio"
_FORANEA_DEL_AREA = "fk_poa_inst_area_area"
_FORANEA_DEL_POA_DEL_AREA = "fk_poa_inst_actividad_poa_area"
_FORANEA_DEL_NODO = "fk_poa_inst_actividad_nodo"
_FORANEA_DE_LA_UNIDAD = "fk_poa_inst_actividad_unidad_medida"


def _poa_area_a_dominio(model: PoaAreaModel) -> PoaArea:
    return PoaArea(
        id=model.id,
        exercise_id=model.ejercicio_id,
        area_id=model.area_id,
        status=PoaAreaStatus(model.estado),
        version=model.version,
    )


def _actividad_a_dominio(
    model: PoaActivityModel, programacion: list[MonthlyScheduleModel]
) -> Activity:
    return Activity(
        id=model.id,
        poa_area_id=model.poa_area_id,
        node_id=model.nodo_id,
        name=model.denominacion,
        unit_id=model.unidad_medida_id,
        evaluation_method=model.metodo_evaluacion,
        annual_target=model.meta_anual,
        monthly=[
            MonthlyTarget(month=mes.mes, target=mes.meta, included=mes.incluido)
            for mes in sorted(programacion, key=lambda fila: fila.mes)
        ],
        version=model.version,
        is_active=model.activo,
    )


def _error_del_poa_del_area(exc: IntegrityError) -> NoReturn:
    if viola_la_restriccion(exc, _UNICO_POA_DEL_AREA_POR_EJERCICIO):
        raise ConflictError("El área ya tiene su POA en este ejercicio.") from exc
    if viola_la_restriccion(exc, _FORANEA_DEL_EJERCICIO):
        raise ValidationError("El ejercicio POA no existe.") from exc
    if viola_la_restriccion(exc, _FORANEA_DEL_AREA):
        raise ValidationError("El área no existe.") from exc
    raise exc


def _error_de_la_actividad(exc: IntegrityError) -> NoReturn:
    if viola_la_restriccion(exc, _FORANEA_DEL_POA_DEL_AREA):
        raise ResourceNotFoundError("El POA del área no existe.") from exc
    if viola_la_restriccion(exc, _FORANEA_DEL_NODO):
        raise ValidationError(
            "La acción del PIDE a la que responde la actividad no existe."
        ) from exc
    if viola_la_restriccion(exc, _FORANEA_DE_LA_UNIDAD):
        raise ValidationError("La unidad de medida no existe.") from exc
    raise exc


class SqlAlchemyPoaAreaRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_poa_area(self, poa_area_id: int) -> PoaArea | None:
        if not cabe_en_el_entero_de_la_base(poa_area_id):
            return None
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaAreaModel, poa_area_id)
            return _poa_area_a_dominio(model) if model is not None else None

    async def find_poa_area(self, exercise_id: int, area_id: int) -> PoaArea | None:
        if not (
            cabe_en_el_entero_de_la_base(exercise_id) and cabe_en_el_entero_de_la_base(area_id)
        ):
            return None
        async with session_scope(self.session_factory) as session:
            model = (
                await session.scalars(
                    select(PoaAreaModel).where(
                        PoaAreaModel.ejercicio_id == exercise_id,
                        PoaAreaModel.area_id == area_id,
                    )
                )
            ).one_or_none()
            return _poa_area_a_dominio(model) if model is not None else None

    async def add_poa_area(self, poa_area: PoaArea) -> None:
        poa_area.validate()
        async with session_scope(self.session_factory) as session:
            model = PoaAreaModel(
                ejercicio_id=poa_area.exercise_id,
                area_id=poa_area.area_id,
                estado=poa_area.status.value,
                version=1,
            )
            session.add(model)
            try:
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_del_poa_del_area(exc)
            poa_area.id = model.id
            poa_area.version = model.version

    async def submit_poa_area_if_version_matches(self, poa_area: PoaArea) -> None:
        poa_area.validate()
        if not cabe_en_el_entero_de_la_base(poa_area.id):
            raise ResourceNotFoundError("El POA del área no existe.")
        async with session_scope(self.session_factory) as session:
            try:
                movidas = (
                    await session.execute(
                        update(PoaAreaModel)
                        .where(
                            PoaAreaModel.id == poa_area.id,
                            PoaAreaModel.version == poa_area.version,
                        )
                        .values(estado=poa_area.status.value, version=poa_area.version + 1)
                    )
                ).rowcount
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_del_poa_del_area(exc)
            if movidas != 1:
                await self._decir_si_no_existe_o_si_lo_movieron(
                    session,
                    PoaAreaModel,
                    poa_area.id,
                    "El POA del área no existe.",
                    "El POA del área fue modificado por otra solicitud: vuelva a cargarlo "
                    "antes de enviarlo.",
                )
        poa_area.version += 1

    async def list_activities(
        self, poa_area_id: int, *, include_inactive: bool = False
    ) -> list[Activity]:
        if not cabe_en_el_entero_de_la_base(poa_area_id):
            return []
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaActivityModel)
                    .where(PoaActivityModel.poa_area_id == poa_area_id)
                    .order_by(PoaActivityModel.id)
                )
            ).all()
            if not models:
                return []
            programacion = await self._programacion_de(session, [model.id for model in models])
        return [
            _actividad_a_dominio(model, programacion.get(model.id, []))
            for model in models
            if include_inactive or model.activo
        ]

    async def get_activity(self, activity_id: int) -> Activity | None:
        if not cabe_en_el_entero_de_la_base(activity_id):
            return None
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaActivityModel, activity_id)
            if model is None:
                return None
            programacion = await self._programacion_de(session, [activity_id])
        return _actividad_a_dominio(model, programacion.get(activity_id, []))

    async def add_activity(self, activity: Activity) -> None:
        activity.validate()
        async with session_scope(self.session_factory) as session:
            model = PoaActivityModel(
                poa_area_id=activity.poa_area_id,
                nodo_id=activity.node_id,
                denominacion=activity.name,
                unidad_medida_id=activity.unit_id,
                metodo_evaluacion=activity.evaluation_method,
                meta_anual=activity.annual_target,
                version=1,
                activo=activity.is_active,
            )
            session.add(model)
            try:
                await session.flush()
                self._sembrar_programacion(session, model.id, activity.monthly)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_de_la_actividad(exc)
            activity.id = model.id
            activity.version = model.version

    async def update_activity_if_version_matches(self, activity: Activity) -> None:
        activity.validate()
        if not cabe_en_el_entero_de_la_base(activity.id):
            raise ResourceNotFoundError("La actividad no existe.")
        async with session_scope(self.session_factory) as session:
            try:
                movidas = (
                    await session.execute(
                        update(PoaActivityModel)
                        .where(
                            PoaActivityModel.id == activity.id,
                            PoaActivityModel.version == activity.version,
                        )
                        .values(
                            nodo_id=activity.node_id,
                            denominacion=activity.name,
                            unidad_medida_id=activity.unit_id,
                            metodo_evaluacion=activity.evaluation_method,
                            meta_anual=activity.annual_target,
                            version=activity.version + 1,
                            activo=activity.is_active,
                        )
                    )
                ).rowcount
                if movidas == 1:
                    await session.execute(
                        delete(MonthlyScheduleModel).where(
                            MonthlyScheduleModel.actividad_id == activity.id
                        )
                    )
                    self._sembrar_programacion(session, activity.id, activity.monthly)
                    await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_de_la_actividad(exc)
            if movidas != 1:
                await self._decir_si_no_existe_o_si_lo_movieron(
                    session,
                    PoaActivityModel,
                    activity.id,
                    "La actividad no existe.",
                    "La actividad fue modificada por otra solicitud: vuelva a cargarla antes "
                    "de guardar.",
                )
        activity.version += 1

    def _sembrar_programacion(
        self, session: AsyncSession, activity_id: int, monthly: list[MonthlyTarget]
    ) -> None:
        for mes in monthly:
            session.add(
                MonthlyScheduleModel(
                    actividad_id=activity_id,
                    mes=mes.month,
                    meta=mes.target,
                    incluido=mes.included,
                )
            )

    async def _programacion_de(
        self, session: AsyncSession, activity_ids: list[int]
    ) -> dict[int, list[MonthlyScheduleModel]]:
        filas = (
            await session.scalars(
                select(MonthlyScheduleModel).where(
                    MonthlyScheduleModel.actividad_id.in_(activity_ids)
                )
            )
        ).all()
        por_actividad: dict[int, list[MonthlyScheduleModel]] = {}
        for fila in filas:
            por_actividad.setdefault(fila.actividad_id, []).append(fila)
        return por_actividad

    async def _decir_si_no_existe_o_si_lo_movieron(
        self,
        session: AsyncSession,
        modelo: type,
        identificador: int,
        no_existe: str,
        lo_movieron: str,
    ) -> NoReturn:
        if await session.get(modelo, identificador) is None:
            raise ResourceNotFoundError(no_existe)
        raise ConflictError(lo_movieron)


class SqlAlchemyAreaLeadership:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def has_person_in_charge(self, area_id: int) -> bool:
        if not cabe_en_el_entero_de_la_base(area_id):
            return False
        async with session_scope(self.session_factory) as session:
            responsable = await session.scalar(
                select(UserModel.id)
                .join(UserRoleModel, UserRoleModel.usuario_id == UserModel.id)
                .where(
                    UserModel.area_id == area_id,
                    UserModel.activo.is_(True),
                    UserRoleModel.rol == Role.RESPONSABLE_AREA.value,
                )
                .limit(1)
            )
        return responsable is not None
