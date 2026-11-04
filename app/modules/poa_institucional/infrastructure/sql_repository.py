from __future__ import annotations

from typing import NoReturn

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.models import UserModel, UserRoleModel
from app.modules.poa_planning.domain.entities import EL_EJERCICIO_POA_NO_EXISTE
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.shared.infrastructure.db.constraints import viola_la_restriccion
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import (
    EL_AREA_NO_EXISTE,
    EL_AREA_YA_TIENE_SU_POA,
    EL_POA_DEL_AREA_NO_EXISTE,
    EL_POA_DEL_AREA_SE_REABRIO_A_LA_VEZ,
    LA_ACTIVIDAD_LA_MOVIERON,
    LO_MOVIERON_AL_ENVIAR,
    LO_MOVIERON_AL_REABRIR,
    Activity,
    CaptureWindow,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    cabe_en_el_entero_de_la_base,
)
from .models import MonthlyScheduleModel, PoaActivityModel, PoaAperturaModel, PoaAreaModel

_FORANEA_DEL_EJERCICIO = "fk_poa_inst_area_ejercicio"
_FORANEA_DE_QUIEN_ABRE = "fk_poa_inst_apertura_abierto_por"
_UNICA_DEL_NUMERO_DE_APERTURA = "uq_poa_inst_apertura_poa_area_numero"
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


def _apertura_a_dominio(model: PoaAperturaModel) -> CaptureWindow:
    return CaptureWindow(
        id=model.id,
        poa_area_id=model.poa_area_id,
        number=model.numero,
        opens_on=model.desde,
        closes_on=model.hasta,
        reason=model.motivo,
        opened_by=model.abierto_por,
    )


def _error_de_la_apertura(exc: IntegrityError) -> NoReturn:
    if viola_la_restriccion(exc, _UNICA_DEL_NUMERO_DE_APERTURA):
        raise ConflictError(EL_POA_DEL_AREA_SE_REABRIO_A_LA_VEZ) from exc
    if viola_la_restriccion(exc, _FORANEA_DE_QUIEN_ABRE):
        raise ValidationError("La persona que abre el POA del área no existe.") from exc
    _error_del_poa_del_area(exc)


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
    if viola_la_restriccion(exc, _FORANEA_DEL_EJERCICIO):
        raise ValidationError(EL_EJERCICIO_POA_NO_EXISTE) from exc
    if viola_la_restriccion(exc, _FORANEA_DEL_AREA):
        raise ValidationError(EL_AREA_NO_EXISTE) from exc
    raise exc


def _error_de_la_actividad(exc: IntegrityError) -> NoReturn:
    if viola_la_restriccion(exc, _FORANEA_DEL_POA_DEL_AREA):
        raise ResourceNotFoundError(EL_POA_DEL_AREA_NO_EXISTE) from exc
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

    async def add_poa_area(self, poa_area: PoaArea, window: CaptureWindow) -> None:
        poa_area.validate()
        window.validate()
        async with session_scope(self.session_factory) as session:
            try:
                abierto = (
                    await session.execute(
                        insert(PoaAreaModel)
                        .values(
                            ejercicio_id=poa_area.exercise_id,
                            area_id=poa_area.area_id,
                            estado=poa_area.status.value,
                            version=1,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[PoaAreaModel.ejercicio_id, PoaAreaModel.area_id]
                        )
                        .returning(PoaAreaModel.id, PoaAreaModel.version)
                    )
                ).one_or_none()
                if abierto is not None:
                    await self._sembrar_apertura(session, abierto[0], window)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_de_la_apertura(exc)
            if abierto is None:
                raise ConflictError(EL_AREA_YA_TIENE_SU_POA)
            poa_area.id, poa_area.version = abierto

    async def reopen_poa_area(self, poa_area: PoaArea, window: CaptureWindow) -> None:
        window.validate()
        if not cabe_en_el_entero_de_la_base(poa_area.id):
            raise ResourceNotFoundError(EL_POA_DEL_AREA_NO_EXISTE)
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
                if movidas == 1:
                    await self._sembrar_apertura(session, poa_area.id, window)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                _error_de_la_apertura(exc)
            if movidas != 1:
                await self._decir_si_no_existe_o_si_lo_movieron(
                    session,
                    PoaAreaModel,
                    poa_area.id,
                    EL_POA_DEL_AREA_NO_EXISTE,
                    LO_MOVIERON_AL_REABRIR,
                )
        poa_area.version += 1

    async def current_capture_window(self, poa_area_id: int) -> CaptureWindow | None:
        historia = await self.capture_windows(poa_area_id)
        return historia[-1] if historia else None

    async def capture_windows(self, poa_area_id: int) -> list[CaptureWindow]:
        if not cabe_en_el_entero_de_la_base(poa_area_id):
            return []
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaAperturaModel)
                    .where(PoaAperturaModel.poa_area_id == poa_area_id)
                    .order_by(PoaAperturaModel.numero)
                )
            ).all()
        return [_apertura_a_dominio(model) for model in models]

    async def _sembrar_apertura(
        self, session: AsyncSession, poa_area_id: int, window: CaptureWindow
    ) -> None:
        model = PoaAperturaModel(
            poa_area_id=poa_area_id,
            numero=window.number,
            desde=window.opens_on,
            hasta=window.closes_on,
            motivo=window.reason,
            abierto_por=window.opened_by,
        )
        session.add(model)
        await session.flush()
        window.id = model.id
        window.poa_area_id = poa_area_id

    async def save_poa_area_if_version_matches(self, poa_area: PoaArea) -> None:
        poa_area.validate()
        if not cabe_en_el_entero_de_la_base(poa_area.id):
            raise ResourceNotFoundError(EL_POA_DEL_AREA_NO_EXISTE)
        async with session_scope(self.session_factory) as session:
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
            if movidas != 1:
                await self._decir_si_no_existe_o_si_lo_movieron(
                    session,
                    PoaAreaModel,
                    poa_area.id,
                    EL_POA_DEL_AREA_NO_EXISTE,
                    LO_MOVIERON_AL_ENVIAR,
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
                    LA_ACTIVIDAD_LA_MOVIERON,
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
