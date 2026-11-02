from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.types import NonNegativeInstitutionalDecimal
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)

from ..application.use_cases.manage_poa_area import OpenedPoa, PoaAreaWithWindow
from ..domain.entities import (
    MESES_DEL_EJERCICIO,
    Activity,
    CaptureWindow,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    sin_la_escala_de_la_base,
    whats_missing_to_submit,
)

IdDeLaBase = Annotated[int, Field(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
MesDelEjercicio = Annotated[int, Field(ge=min(MESES_DEL_EJERCICIO), le=max(MESES_DEL_EJERCICIO))]
VersionSobreLaQueSeEdita = Annotated[int, Field(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]

ATRIBUTO_DEL_DOMINIO = {
    "denominacion": "name",
    "nodo_id": "node_id",
    "unidad_medida_id": "unit_id",
    "metodo_evaluacion": "evaluation_method",
    "meta_anual": "annual_target",
    "programacion": "monthly",
    "activa": "is_active",
}

CAMPOS_QUE_NO_ADMITEN_NULO = ("denominacion", "programacion", "activa")

EL_NULO_NO_ES_LEGAL_AQUI = "Este campo no admite nulo: omítalo para dejarlo como está."


def _sin_la_rama_del_nulo(esquema: dict[str, Any]) -> None:
    ramas = [rama for rama in esquema.pop("anyOf", []) if rama != {"type": "null"}]
    esquema.pop("default", None)
    if len(ramas) == 1:
        esquema.update(ramas[0])
    elif ramas:
        esquema["anyOf"] = ramas


def _que_el_esquema_tampoco_admita_nulo() -> Any:
    return Field(default=None, json_schema_extra=_sin_la_rama_del_nulo)


class MesProgramadoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mes: MesDelEjercicio
    meta: NonNegativeInstitutionalDecimal = Decimal(0)
    incluido: bool = True

    def to_domain(self) -> MonthlyTarget:
        return MonthlyTarget(month=self.mes, target=self.meta, included=self.incluido)


class ActividadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    denominacion: str | None = _que_el_esquema_tampoco_admita_nulo()
    nodo_id: IdDeLaBase | None = None
    unidad_medida_id: IdDeLaBase | None = None
    metodo_evaluacion: str | None = None
    meta_anual: NonNegativeInstitutionalDecimal | None = None
    programacion: list[MesProgramadoRequest] | None = _que_el_esquema_tampoco_admita_nulo()
    activa: bool | None = _que_el_esquema_tampoco_admita_nulo()

    @field_validator(*CAMPOS_QUE_NO_ADMITEN_NULO)
    @classmethod
    def rechazar_el_nulo_explicito(cls, valor: Any) -> Any:
        if valor is None:
            raise ValueError(EL_NULO_NO_ES_LEGAL_AQUI)
        return valor

    def lo_que_se_mando(self) -> dict[str, Any]:
        return {
            ATRIBUTO_DEL_DOMINIO[campo]: self._valor_de_dominio(campo)
            for campo in ATRIBUTO_DEL_DOMINIO
            if campo in self.model_fields_set
        }

    def _valor_de_dominio(self, campo: str) -> Any:
        valor = getattr(self, campo)
        if campo == "programacion":
            return [mes.to_domain() for mes in valor]
        return valor


class CrearActividadRequest(ActividadRequest):
    denominacion: str


class ActualizarActividadRequest(ActividadRequest):
    version: VersionSobreLaQueSeEdita


class PresentarPoaDelAreaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionSobreLaQueSeEdita


class AbrirElPoaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    areas: Annotated[list[IdDeLaBase], Field(min_length=1)] | None
    desde: date
    hasta: date


class ReabrirElPoaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desde: date
    hasta: date
    motivo: Annotated[str, Field(min_length=1)]


class PoaDelAreaAbiertoRespuesta(BaseModel):
    id: int
    ejercicio_id: int
    area_id: int
    estado: PoaAreaStatus
    version: int
    abierto_desde: date | None
    abierto_hasta: date | None
    periodos_habilitados: int

    @classmethod
    def from_domain(cls, abierto: PoaAreaWithWindow) -> PoaDelAreaAbiertoRespuesta:
        return cls(
            id=abierto.poa_area.id,
            ejercicio_id=abierto.poa_area.exercise_id,
            area_id=abierto.poa_area.area_id,
            estado=abierto.poa_area.status,
            version=abierto.poa_area.version,
            abierto_desde=None if abierto.window is None else abierto.window.opens_on,
            abierto_hasta=None if abierto.window is None else abierto.window.closes_on,
            periodos_habilitados=0 if abierto.window is None else abierto.window.number,
        )


class AperturaDelPoaRespuesta(BaseModel):
    ejercicio_id: int
    abiertos: list[PoaDelAreaAbiertoRespuesta]
    ya_estaban_abiertos: list[PoaDelAreaAbiertoRespuesta]

    @classmethod
    def from_domain(cls, ejercicio_id: int, reparto: OpenedPoa) -> AperturaDelPoaRespuesta:
        return cls(
            ejercicio_id=ejercicio_id,
            abiertos=[PoaDelAreaAbiertoRespuesta.from_domain(uno) for uno in reparto.opened],
            ya_estaban_abiertos=[
                PoaDelAreaAbiertoRespuesta.from_domain(uno) for uno in reparto.already_open
            ],
        )


class MesProgramadoRespuesta(BaseModel):
    mes: int
    meta: Decimal
    incluido: bool

    @field_serializer("meta")
    def dicha_sin_la_escala_de_la_base(self, meta: Decimal) -> str:
        return sin_la_escala_de_la_base(meta)

    @classmethod
    def from_domain(cls, mes: MonthlyTarget) -> MesProgramadoRespuesta:
        return cls(mes=mes.month, meta=mes.target, incluido=mes.included)


class ActividadRespuesta(BaseModel):
    id: int
    version: int
    nodo_id: int | None
    denominacion: str
    unidad_medida_id: int | None
    metodo_evaluacion: str | None
    meta_anual: Decimal | None
    programacion: list[MesProgramadoRespuesta]
    activa: bool
    falta_para_presentar: list[str]

    @field_serializer("meta_anual")
    def dicha_sin_la_escala_de_la_base(self, meta: Decimal | None) -> str | None:
        return None if meta is None else sin_la_escala_de_la_base(meta)

    @classmethod
    def from_domain(cls, activity: Activity) -> ActividadRespuesta:
        return cls(
            falta_para_presentar=whats_missing_to_submit(activity),
            id=activity.id,
            version=activity.version,
            nodo_id=activity.node_id,
            denominacion=activity.name,
            unidad_medida_id=activity.unit_id,
            metodo_evaluacion=activity.evaluation_method,
            meta_anual=activity.annual_target,
            programacion=[MesProgramadoRespuesta.from_domain(mes) for mes in activity.months()],
            activa=activity.is_active,
        )


class PoaDelAreaRespuesta(BaseModel):
    id: int
    ejercicio_id: int
    area_id: int
    estado: PoaAreaStatus
    version: int
    abierto_desde: date | None
    abierto_hasta: date | None
    periodos_habilitados: int
    esta_abierto: bool
    actividades: list[ActividadRespuesta]
    falta_para_presentar: list[str]

    @classmethod
    def from_domain(
        cls,
        poa_area: PoaArea,
        actividades: list[Activity],
        *,
        falta_para_presentar: list[str],
        ventana: CaptureWindow | None,
        hoy: date,
    ) -> PoaDelAreaRespuesta:
        return cls(
            id=poa_area.id,
            ejercicio_id=poa_area.exercise_id,
            area_id=poa_area.area_id,
            estado=poa_area.status,
            version=poa_area.version,
            abierto_desde=None if ventana is None else ventana.opens_on,
            abierto_hasta=None if ventana is None else ventana.closes_on,
            periodos_habilitados=0 if ventana is None else ventana.number,
            esta_abierto=ventana is not None and ventana.includes(hoy),
            actividades=[ActividadRespuesta.from_domain(una) for una in actividades],
            falta_para_presentar=falta_para_presentar,
        )
