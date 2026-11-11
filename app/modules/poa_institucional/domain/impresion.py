from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
)

from .entities import Activity, sin_la_escala_de_la_base

SIN_ACCION = "Actividades sin acción del Programa Institucional de Desarrollo"

SIN_UNIDAD = "Sin unidad"

SIN_RESPONSABLE = "Sin responsable designado"

NOTA_DEL_BORRADOR = (
    "Esta impresión refleja lo capturado hasta el momento. El POA del área todavía no se "
    "presenta a la Dirección de Planeación, de modo que sus actividades pueden cambiar."
)

NOTA_DE_LO_PRESENTADO = (
    "El POA del área ya fue presentado a la Dirección de Planeación: sus actividades no "
    "admiten cambios."
)

MESES_DEL_EJERCICIO = tuple(range(1, 13))


@dataclass(frozen=True)
class RenglonDeActividad:
    numero: str
    denominacion: str
    meses: dict[int, str]
    unidad: str
    programado: str
    monto: str


@dataclass(frozen=True)
class BloqueDeLaAccion:
    eje: str
    estrategia: str
    titulo: str
    actividades: list[RenglonDeActividad]


@dataclass(frozen=True)
class PoaParaImprimir:
    area: str
    responsable: str
    anio: int
    elaborado_el: date
    nota: str
    bloques: list[BloqueDeLaAccion]
    total: str

    @property
    def cuantas_actividades(self) -> int:
        return sum(len(bloque.actividades) for bloque in self.bloques)


def armar_el_poa_para_imprimir(
    *,
    area: str,
    responsable: str | None,
    anio: int,
    elaborado_el: date,
    presentado: bool,
    actividades: Sequence[Activity],
    nodos: Sequence[StrategicNode],
    unidades: Mapping[int, tuple[str, str]],
) -> PoaParaImprimir:
    por_id = {nodo.id: nodo for nodo in nodos}
    vigentes = [una for una in actividades if una.is_active]
    agrupadas: dict[int | None, list[Activity]] = {}
    for una in vigentes:
        agrupadas.setdefault(una.node_id if una.node_id in por_id else None, []).append(una)

    bloques = [
        _bloque(accion_id, suyas, por_id, unidades)
        for accion_id, suyas in sorted(agrupadas.items(), key=lambda par: _orden(par[0], por_id))
    ]
    return PoaParaImprimir(
        area=area,
        responsable=responsable or SIN_RESPONSABLE,
        anio=anio,
        elaborado_el=elaborado_el,
        nota=NOTA_DE_LO_PRESENTADO if presentado else NOTA_DEL_BORRADOR,
        bloques=bloques,
        total=dicho_el_monto(
            sum((una.requested_amount or Decimal(0) for una in vigentes), start=Decimal(0))
        ),
    )


def _bloque(
    accion_id: int | None,
    actividades: Sequence[Activity],
    por_id: Mapping[int, StrategicNode],
    unidades: Mapping[int, tuple[str, str]],
) -> BloqueDeLaAccion:
    accion = por_id.get(accion_id) if accion_id is not None else None
    eje = _ancestro(accion, por_id, NodeKind.EJE)
    estrategia = _ancestro(accion, por_id, NodeKind.LINEA_ESTRATEGICA)
    return BloqueDeLaAccion(
        eje="" if eje is None else eje.key,
        estrategia="" if estrategia is None else estrategia.key,
        titulo=SIN_ACCION if accion is None else f"{accion.key} · {accion.name}",
        actividades=[
            _renglon(cual, una, unidades) for cual, una in enumerate(actividades, start=1)
        ],
    )


def _renglon(
    cual: int, actividad: Activity, unidades: Mapping[int, tuple[str, str]]
) -> RenglonDeActividad:
    incluidos = [mes for mes in actividad.monthly if mes.included]
    programado = sum((mes.target for mes in incluidos), start=Decimal(0))
    return RenglonDeActividad(
        numero=str(cual),
        denominacion=actividad.name,
        meses={mes.month: sin_la_escala_de_la_base(mes.target) for mes in incluidos},
        unidad=_dicha_la_unidad(actividad.unit_id, programado, unidades),
        programado=sin_la_escala_de_la_base(programado),
        monto=dicho_el_monto(actividad.requested_amount or Decimal(0)),
    )


def dicho_el_monto(monto: Decimal) -> str:
    return f"${monto:,.2f}"


def _dicha_la_unidad(
    unidad_id: int | None, programado: Decimal, unidades: Mapping[int, tuple[str, str]]
) -> str:
    if unidad_id is None or unidad_id not in unidades:
        return SIN_UNIDAD
    singular, plural = unidades[unidad_id]
    return singular if programado == 1 else plural


def _ancestro(
    nodo: StrategicNode | None, por_id: Mapping[int, StrategicNode], nivel: NodeKind
) -> StrategicNode | None:
    vistos: set[int] = set()
    actual = nodo
    while actual is not None and actual.id not in vistos:
        if actual.kind == nivel:
            return actual
        vistos.add(actual.id)
        actual = por_id.get(actual.parent_id) if actual.parent_id is not None else None
    return None


def _orden(
    accion_id: int | None, por_id: Mapping[int, StrategicNode]
) -> tuple[int, list[int], str]:
    if accion_id is None:
        return (1, [], "")
    accion = por_id[accion_id]
    return (0, _clave_numerica(accion.key), accion.key)


def _clave_numerica(clave: str) -> list[int]:
    partes = []
    for parte in clave.replace(" ", "").split("."):
        if parte.isdigit():
            partes.append(int(parte))
    return partes
