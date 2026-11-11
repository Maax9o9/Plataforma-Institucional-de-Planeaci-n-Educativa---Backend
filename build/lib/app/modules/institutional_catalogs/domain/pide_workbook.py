from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.shared.domain.captured_text import recortado_sin_invisibles
from app.shared.domain.exceptions import ValidationError

from .strategic_tree_entities import KEY_MAX_LENGTH, NodeKind

HOJA_DE_ACCIONES = "Líneas, acciones e indicadores"
HOJA_DE_OBJETIVOS = "Ejes y objetivos"

PARTES_DE_LA_LINEA = 4
PARTES_DE_LA_ACCION = 5

PROBLEMAS_QUE_SE_ENUMERAN = 12

_CLAVE_Y_TEXTO = re.compile(r"^(\d+(?:\.\d+)*)\.?\s*[-–—.)]?\s*(.*)$", re.DOTALL)
_EJE_Y_TEXTO = re.compile(r"^Eje\s+(\d+)\.?\s*[-–—.)]?\s*(.*)$", re.IGNORECASE | re.DOTALL)

_NIVEL_POR_PARTES = {
    1: NodeKind.EJE,
    2: NodeKind.OBJETIVO_GENERAL,
    3: NodeKind.OBJETIVO_ESPECIFICO,
    PARTES_DE_LA_LINEA: NodeKind.LINEA_ESTRATEGICA,
    PARTES_DE_LA_ACCION: NodeKind.ACCION,
}

_NOMBRE_SUPLIDO = {
    NodeKind.OBJETIVO_GENERAL: "Objetivo general",
    NodeKind.OBJETIVO_ESPECIFICO: "Objetivo específico",
}


class WorkbookShapeError(ValidationError):
    code = "PIDE_WORKBOOK_SHAPE"


@dataclass(frozen=True, kw_only=True)
class FilaDeAcciones:
    numero: int
    eje: str | None
    linea: str | None
    accion: str | None
    indicador: str | None


@dataclass(frozen=True, kw_only=True)
class FilaDeObjetivos:
    numero: int
    eje: str | None
    objetivo_general: str | None
    clave_especifico: str | None
    objetivo_especifico: str | None


@dataclass(kw_only=True)
class NodoPlaneado:
    kind: NodeKind
    key: str
    name: str
    order: int
    parent_key: str | None
    indicator_formula: str | None = None


@dataclass(kw_only=True)
class PlanDeCarga:
    nodos: list[NodoPlaneado] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def cuantos_por_nivel(self) -> dict[str, int]:
        cuenta = {kind.value: 0 for kind in NodeKind}
        for nodo in self.nodos:
            cuenta[nodo.kind.value] += 1
        return cuenta


def limpio(valor: object | None) -> str | None:
    if valor is None:
        return None
    texto = recortado_sin_invisibles(str(valor))
    return texto or None


def clave_y_denominacion(texto: str) -> tuple[str, str] | None:
    encontrado = _CLAVE_Y_TEXTO.match(texto.strip())
    if encontrado is None:
        return None
    clave = encontrado.group(1)
    denominacion = recortado_sin_invisibles(encontrado.group(2))
    return clave, denominacion


def clave_y_denominacion_del_eje(texto: str) -> tuple[str, str] | None:
    encontrado = _EJE_Y_TEXTO.match(texto.strip())
    if encontrado is None:
        return clave_y_denominacion(texto)
    return encontrado.group(1), recortado_sin_invisibles(encontrado.group(2))


def clave_del_padre(clave: str) -> str | None:
    partes = clave.split(".")
    return ".".join(partes[:-1]) if len(partes) > 1 else None


def plan_de_carga(
    filas_de_acciones: list[FilaDeAcciones],
    filas_de_objetivos: list[FilaDeObjetivos] | None = None,
) -> PlanDeCarga:
    nombres = _nombres_de_los_objetivos(filas_de_objetivos or [])
    problemas: list[str] = []
    plan = PlanDeCarga()
    puestos: dict[str, NodoPlaneado] = {}
    hermanos: dict[str | None, int] = {}
    claves_vistas: dict[str, int] = {}

    def poner(kind: NodeKind, clave: str, denominacion: str) -> NodoPlaneado:
        ya = puestos.get(clave)
        if ya is not None:
            return ya
        padre = clave_del_padre(clave)
        hermanos[padre] = hermanos.get(padre, 0) + 1
        nodo = NodoPlaneado(
            kind=kind,
            key=clave,
            name=denominacion,
            order=hermanos[padre],
            parent_key=padre,
        )
        puestos[clave] = nodo
        plan.nodos.append(nodo)
        return nodo

    def poner_con_ancestros(clave: str, denominacion: str, eje: tuple[str, str]) -> NodoPlaneado:
        clave_del_eje, denominacion_del_eje = eje
        poner(NodeKind.EJE, clave_del_eje, denominacion_del_eje)
        partes = clave.split(".")
        for cuantas in range(2, len(partes)):
            intermedia = ".".join(partes[:cuantas])
            kind = _NIVEL_POR_PARTES[cuantas]
            poner(kind, intermedia, nombres.get(intermedia) or _suplido(kind, intermedia))
        return poner(_NIVEL_POR_PARTES[len(partes)], clave, denominacion)

    if not filas_de_acciones:
        raise WorkbookShapeError(
            f"La hoja «{HOJA_DE_ACCIONES}» no trae ninguna fila con acciones."
        )

    for fila in filas_de_acciones:
        if fila.accion is None:
            continue
        donde = f"fila {fila.numero}"
        if fila.eje is None:
            problemas.append(f"En la {donde} la acción no dice a qué eje pertenece.")
            continue
        if fila.linea is None:
            problemas.append(f"En la {donde} la acción no dice de qué línea estratégica cuelga.")
            continue

        eje = clave_y_denominacion_del_eje(fila.eje)
        if eje is None or not eje[1]:
            problemas.append(
                f"En la {donde} el eje «{_recorte(fila.eje)}» no trae número y nombre."
            )
            continue

        linea = clave_y_denominacion(fila.linea)
        if linea is None or not linea[1]:
            problemas.append(
                f"En la {donde} la línea estratégica «{_recorte(fila.linea)}» no empieza con su"
                " clave numérica."
            )
            continue
        if len(linea[0].split(".")) != PARTES_DE_LA_LINEA:
            problemas.append(
                f"En la {donde} la clave «{linea[0]}» de la línea estratégica no tiene las"
                f" {PARTES_DE_LA_LINEA} partes que la identifican, como «1.1.1.1»."
            )
            continue

        accion = clave_y_denominacion(fila.accion)
        if accion is None or not accion[1]:
            problemas.append(
                f"En la {donde} la acción «{_recorte(fila.accion)}» no empieza con su clave"
                " numérica."
            )
            continue
        if len(accion[0].split(".")) != PARTES_DE_LA_ACCION:
            problemas.append(
                f"En la {donde} la clave «{accion[0]}» de la acción no tiene las"
                f" {PARTES_DE_LA_ACCION} partes que la identifican, como «1.1.1.1.1»."
            )
            continue
        if len(accion[0]) > KEY_MAX_LENGTH:
            problemas.append(
                f"En la {donde} la clave «{accion[0]}» supera los {KEY_MAX_LENGTH} caracteres."
            )
            continue
        if clave_del_padre(accion[0]) != linea[0]:
            problemas.append(
                f"En la {donde} la acción «{accion[0]}» no cuelga de la línea estratégica"
                f" «{linea[0]}» con la que aparece."
            )
            continue
        if not linea[0].startswith(f"{eje[0]}."):
            problemas.append(
                f"En la {donde} la línea estratégica «{linea[0]}» no pertenece al"
                f" eje {eje[0]} con el que aparece."
            )
            continue
        repetida = claves_vistas.get(accion[0])
        if repetida is not None:
            problemas.append(
                f"En la {donde} la clave «{accion[0]}» ya se había usado en la fila {repetida}."
            )
            continue

        claves_vistas[accion[0]] = fila.numero
        poner_con_ancestros(linea[0], linea[1], eje)
        nodo = poner_con_ancestros(accion[0], accion[1], eje)
        nodo.indicator_formula = fila.indicador

        if fila.indicador is None:
            plan.avisos.append(f"La acción «{accion[0]}» se carga sin fórmula del indicador.")

    if problemas:
        raise WorkbookShapeError(_dicho(problemas))

    for nodo in plan.nodos:
        if nodo.kind in _NOMBRE_SUPLIDO and nodo.name == _suplido(nodo.kind, nodo.key):
            plan.avisos.append(
                f"El {_NOMBRE_SUPLIDO[nodo.kind].lower()} «{nodo.key}» no aparece en la hoja"
                f" «{HOJA_DE_OBJETIVOS}»: se carga con un nombre provisional que conviene"
                " corregir."
            )

    return plan


def _nombres_de_los_objetivos(filas: list[FilaDeObjetivos]) -> dict[str, str]:
    nombres: dict[str, str] = {}
    for fila in filas:
        if fila.objetivo_general is not None:
            general = clave_y_denominacion(_sin_encabezado(fila.objetivo_general))
            if general is not None and general[1]:
                nombres.setdefault(general[0], general[1])
        if fila.clave_especifico is not None and fila.objetivo_especifico is not None:
            especifico = clave_y_denominacion(fila.clave_especifico)
            if especifico is not None:
                nombres.setdefault(especifico[0], fila.objetivo_especifico)
    return nombres


def _sin_encabezado(texto: str) -> str:
    sin_rotulo = re.sub(
        r"^(\d+(?:\.\d+)*)\.?\s*Objetivo\s+General\s*",
        r"\1 ",
        texto.strip(),
        flags=re.IGNORECASE,
    )
    return recortado_sin_invisibles(sin_rotulo)


def _suplido(kind: NodeKind, clave: str) -> str:
    return f"{_NOMBRE_SUPLIDO.get(kind, 'Nodo')} {clave}"


def _recorte(texto: str) -> str:
    limpio_ = " ".join(texto.split())
    return limpio_ if len(limpio_) <= 60 else f"{limpio_[:57]}…"


def _dicho(problemas: list[str]) -> str:
    cuantos = len(problemas)
    cabeza = problemas[:PROBLEMAS_QUE_SE_ENUMERAN]
    enumerados = " ".join(cabeza)
    if cuantos <= PROBLEMAS_QUE_SE_ENUMERAN:
        return f"El archivo no se cargó porque tiene {cuantos} problema(s). {enumerados}"
    restantes = cuantos - PROBLEMAS_QUE_SE_ENUMERAN
    return (
        f"El archivo no se cargó porque tiene {cuantos} problemas. {enumerados}"
        f" Y {restantes} más del mismo tipo."
    )
