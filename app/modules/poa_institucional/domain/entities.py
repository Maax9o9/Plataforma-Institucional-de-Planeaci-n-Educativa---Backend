from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
    cabe_en_el_entero_de_la_base,
)
from app.shared.domain.calendar import el_dia_en_letras
from app.shared.domain.captured_text import recortado_sin_invisibles
from app.shared.domain.exceptions import InvalidStateError, ValidationError

MESES_DEL_EJERCICIO = tuple(range(1, 13))

DECIMALES_DE_LA_META = 4
ENTEROS_DE_LA_META = 14
META_MAS_ALTA_QUE_CABE = Decimal(10) ** ENTEROS_DE_LA_META - Decimal(1).scaleb(
    -DECIMALES_DE_LA_META
)

NIVEL_DE_LA_ACTIVIDAD = NodeKind.ACCION

EL_POA_DEL_AREA_NO_SE_PUEDE_ENVIAR = "El POA del área no se puede enviar. "

EL_AREA_NO_EXISTE = "El área no existe. Revise el catálogo de áreas antes de continuar."

EL_AREA_YA_TIENE_SU_POA = "El área ya tiene su Programa Operativo Anual en este ejercicio."

EL_POA_DEL_AREA_SE_REABRIO_A_LA_VEZ = (
    "Otra solicitud habilitó un nuevo periodo de captura al mismo tiempo. Vuelva a consultar "
    "el Programa Operativo Anual del área antes de intentarlo de nuevo."
)

EL_POA_DEL_AREA_NO_EXISTE = "El Programa Operativo Anual del área no existe."

LO_MOVIERON_AL_ENVIAR = (
    "El Programa Operativo Anual del área fue modificado por otra solicitud. Vuelva a "
    "consultarlo antes de presentarlo."
)

LO_MOVIERON_AL_REABRIR = (
    "El Programa Operativo Anual del área fue modificado por otra solicitud. Vuelva a "
    "consultarlo antes de habilitar un nuevo periodo de captura."
)

LA_ACTIVIDAD_LA_MOVIERON = (
    "La actividad fue modificada por otra solicitud. Vuelva a consultarla antes de guardar."
)

EL_PRIMER_PERIODO_ES_EL_UNO = (
    "El primer periodo de captura de un Programa Operativo Anual es el número 1 y los "
    "siguientes continúan a partir de ahí."
)

UN_PERIODO_NUEVO_REQUIERE_MOTIVO = (
    "La habilitación de un nuevo periodo requiere un motivo: queda asentado en el expediente "
    "del programa junto con la fecha y la persona que lo autoriza."
)

SOLICITE_UN_PERIODO_NUEVO = "Solicite a la Dirección de Planeación que habilite un nuevo periodo."


class EstadoDelRegistro(StrEnum):
    SIN_HABILITAR = "sin_habilitar"
    POR_INICIAR = "por_iniciar"
    ABIERTO = "abierto"
    CONCLUIDO = "concluido"


class PoaAreaStatus(StrEnum):
    BORRADOR = "borrador"
    ENVIADO = "enviado"


@dataclass(kw_only=True)
class MonthlyTarget:
    month: int
    target: Decimal = Decimal(0)
    included: bool = True


@dataclass(kw_only=True)
class PoaArea:
    id: int = 0
    exercise_id: int
    area_id: int
    status: PoaAreaStatus = PoaAreaStatus.BORRADOR
    version: int = 1

    def validate(self) -> None:
        try:
            self.status = PoaAreaStatus(self.status)
        except ValueError:
            raise ValidationError(
                f"El estado «{self.status}» no es uno de los dos del POA del área: "
                + ", ".join(estado.value for estado in PoaAreaStatus)
                + "."
            ) from None
        for campo, numero in (("ejercicio", self.exercise_id), ("área", self.area_id)):
            if not cabe_en_el_entero_de_la_base(numero):
                raise ValidationError(
                    f"El «{campo}» del POA del área no cabe en el entero de la base: {numero}."
                )


@dataclass(kw_only=True)
class CaptureWindow:
    id: int = 0
    poa_area_id: int = 0
    number: int = 1
    opens_on: date
    closes_on: date
    reason: str | None = None
    opened_by: int | None = None

    def validate(self) -> None:
        if self.number < 1:
            raise ValidationError(f"{EL_PRIMER_PERIODO_ES_EL_UNO} Llegó el número {self.number}.")
        if self.closes_on < self.opens_on:
            raise ValidationError(
                f"El periodo de captura concluiría el {el_dia_en_letras(self.closes_on)}, antes "
                f"del {el_dia_en_letras(self.opens_on)} en que inicia. Revise las dos fechas."
            )
        self.reason = recortado_sin_invisibles(self.reason or "") or None
        if self.number > 1 and self.reason is None:
            raise ValidationError(UN_PERIODO_NUEVO_REQUIERE_MOTIVO)
        for campo, numero in (
            ("Programa Operativo Anual del área", self.poa_area_id),
            ("persona que lo autoriza", self.opened_by),
        ):
            if numero is not None and not cabe_en_el_entero_de_la_base(numero):
                raise ValidationError(
                    f"El identificador de la «{campo}» no cabe en el entero de la base: {numero}."
                )

    def includes(self, day: date) -> bool:
        return self.opens_on <= day <= self.closes_on


def estado_del_registro(window: CaptureWindow | None, *, today: date) -> EstadoDelRegistro:
    if window is None:
        return EstadoDelRegistro.SIN_HABILITAR
    if today < window.opens_on:
        return EstadoDelRegistro.POR_INICIAR
    if today > window.closes_on:
        return EstadoDelRegistro.CONCLUIDO
    return EstadoDelRegistro.ABIERTO


def dias_naturales_restantes(window: CaptureWindow | None, *, today: date) -> int | None:
    if window is None or estado_del_registro(window, today=today) is not EstadoDelRegistro.ABIERTO:
        return None
    return (window.closes_on - today).days


def ensure_capture_is_open(
    window: CaptureWindow | None, *, area_name: str | None, today: date
) -> None:
    if window is not None and window.includes(today):
        return
    if window is None:
        raise InvalidStateError(el_registro_no_esta_habilitado(area_name))
    if today < window.opens_on:
        raise InvalidStateError(
            f"{_el_periodo_del_programa(area_name)} inicia el {el_dia_en_letras(window.opens_on)}. "
            "Podrá registrar sus actividades a partir de esa fecha."
        )
    raise InvalidStateError(
        f"{_el_periodo_del_programa(area_name)} concluyó el "
        f"{el_dia_en_letras(window.closes_on)}. {SOLICITE_UN_PERIODO_NUEVO}"
    )


def el_registro_no_esta_habilitado(area_name: str | None) -> str:
    de_quien = "El área" if area_name is None else f"El área de {area_name}"
    return (
        f"{de_quien} todavía no tiene habilitado el registro de actividades en este ejercicio. "
        "La Dirección de Planeación debe habilitarlo antes de que pueda capturarse."
    )


def el_programa_del_area_sin_abrir(area_name: str | None) -> str:
    de_quien = "El área" if area_name is None else f"El área de {area_name}"
    return (
        f"{de_quien} no tiene un Programa Operativo Anual abierto en este ejercicio. Ábralo "
        "antes de habilitar un nuevo periodo de captura."
    )


def _el_periodo_del_programa(area_name: str | None) -> str:
    de_quien = "" if area_name is None else f" de {area_name}"
    return f"El periodo de captura del Programa Operativo Anual{de_quien}"


@dataclass(kw_only=True)
class Activity:
    id: int = 0
    poa_area_id: int
    node_id: int | None = None
    name: str
    unit_id: int | None = None
    evaluation_method: str | None = None
    annual_target: Decimal | None = None
    monthly: list[MonthlyTarget] = field(default_factory=list)
    version: int = 1
    is_active: bool = True

    def validate(self) -> None:
        self.name = recortado_sin_invisibles(self.name)
        if not self.name:
            raise ValidationError("La denominación de la actividad es obligatoria.")
        if "\0" in self.name:
            raise ValidationError("La denominación de la actividad no admite el carácter nulo.")
        if self.evaluation_method is not None:
            self.evaluation_method = recortado_sin_invisibles(self.evaluation_method) or None
        if self.evaluation_method is not None and "\0" in self.evaluation_method:
            raise ValidationError("El método de evaluación no admite el carácter nulo.")
        for campo, numero in (
            ("POA del área", self.poa_area_id),
            ("acción del PIDE", self.node_id),
            ("unidad de medida", self.unit_id),
        ):
            if numero is not None and not cabe_en_el_entero_de_la_base(numero):
                raise ValidationError(
                    f"La «{campo}» de la actividad no cabe en el entero de la base: {numero}."
                )
        if self.annual_target is not None:
            _exigir_meta_que_la_base_guarda_sin_redondear(
                self.annual_target, f"La meta anual de «{self.name}»"
            )
        self._validar_programacion()

    def _validar_programacion(self) -> None:
        if not self.monthly:
            return
        meses = [mes.month for mes in self.monthly]
        if sorted(meses) != list(MESES_DEL_EJERCICIO):
            raise ValidationError(
                f"La programación de «{self.name}» son los doce meses del ejercicio, "
                f"una sola vez cada uno: llegaron {len(meses)} "
                f"({', '.join(str(mes) for mes in meses)})."
            )
        for mes in self.monthly:
            _exigir_meta_que_la_base_guarda_sin_redondear(
                mes.target, f"La meta del mes {mes.month} de «{self.name}»"
            )
            if not mes.included and mes.target != 0:
                raise ValidationError(
                    f"El mes {mes.month} de «{self.name}» queda fuera de la programación y "
                    f"con una meta de {sin_la_escala_de_la_base(mes.target)}: sacar un mes de la "
                    "programación también limpia su número, así que envíelo en cero en el mismo "
                    "guardado."
                )

    def included_sum(self) -> Decimal:
        return sum((mes.target for mes in self.monthly if mes.included), Decimal(0))

    def months(self) -> list[MonthlyTarget]:
        return sorted(self.monthly, key=lambda mes: mes.month)


def sin_la_escala_de_la_base(meta: Decimal) -> str:
    return f"{meta.normalize():f}" if meta.is_finite() else f"{meta}"


def _exigir_meta_que_la_base_guarda_sin_redondear(meta: Decimal, de_quien: str) -> None:
    dicha = sin_la_escala_de_la_base(meta)
    if not meta.is_finite():
        raise ValidationError(f"{de_quien} no es un número finito: {dicha}.")
    if meta < 0:
        raise ValidationError(f"{de_quien} no puede ser negativa: {dicha}.")
    if meta > META_MAS_ALTA_QUE_CABE:
        raise ValidationError(
            f"{de_quien} no cabe en la columna de la base, que admite hasta "
            f"{sin_la_escala_de_la_base(META_MAS_ALTA_QUE_CABE)}: {dicha}."
        )
    if -meta.as_tuple().exponent > DECIMALES_DE_LA_META:
        raise ValidationError(
            f"{de_quien} trae más de {DECIMALES_DE_LA_META} decimales y la base la redondearía "
            f"sin avisar: {dicha}."
        )


def ensure_node_can_be_chosen(node: StrategicNode | None) -> None:
    if node is None:
        raise ValidationError("La acción del PIDE a la que responde la actividad no existe.")
    if node.kind is not NIVEL_DE_LA_ACTIVIDAD:
        raise ValidationError(
            f"Una actividad responde a un nodo de nivel «{NIVEL_DE_LA_ACTIVIDAD.value}», y "
            f"«{node.key}» es de nivel «{node.kind.value}»."
        )
    if not node.is_active:
        raise ValidationError(
            f"«{node.key}» está retirado del PIDE: lo retirado no se puede elegir al formular. "
            "Las actividades que ya responden a él se conservan."
        )


def ensure_is_still_a_draft(poa_area: PoaArea) -> None:
    if poa_area.status is PoaAreaStatus.BORRADOR:
        return
    raise InvalidStateError(
        "El POA del área ya fue enviado: ni sus actividades admiten cambios ni se envía otra vez."
    )


def whats_missing_to_submit(activity: Activity) -> list[str]:
    faltas: list[str] = []
    if activity.node_id is None:
        faltas.append("la acción del PIDE a la que responde")
    if activity.unit_id is None:
        faltas.append("la unidad de medida")
    if not recortado_sin_invisibles(activity.evaluation_method or ""):
        faltas.append("el método de evaluación")
    if activity.annual_target is None:
        faltas.append("la meta anual")
    meses = sorted(mes.month for mes in activity.monthly)
    if meses != list(MESES_DEL_EJERCICIO):
        faltas.append(f"la programación de los doce meses (trae {len(meses)})")
    elif activity.annual_target is not None:
        sumado = activity.included_sum()
        if sumado != activity.annual_target:
            faltas.append(
                "que sus meses incluidos en la programación sumen la meta anual: suman "
                f"{sin_la_escala_de_la_base(sumado)} "
                f"de {sin_la_escala_de_la_base(activity.annual_target)}"
            )
    return faltas


def reasons_it_cannot_be_submitted(
    activities: list[Activity], *, area_has_person_in_charge: bool
) -> list[str]:
    razones: list[str] = []
    if not area_has_person_in_charge:
        razones.append(
            "El área no tiene responsable asignado y nadie respondería por este POA: "
            "asígnele el rol de responsable de área a alguien del área."
        )
    activas = [activity for activity in activities if activity.is_active]
    if not activas:
        razones.append("No tiene ninguna actividad activa.")
    incompletas = [(activity, whats_missing_to_submit(activity)) for activity in activas]
    incompletas = [(activity, faltas) for activity, faltas in incompletas if faltas]
    if incompletas:
        cuantas = (
            "1 actividad está incompleta"
            if len(incompletas) == 1
            else f"{len(incompletas)} actividades están incompletas"
        )
        detalle = " ".join(
            f"A «{activity.name}» le falta {_enumerado(faltas)}."
            for activity, faltas in incompletas
        )
        razones.append(f"{cuantas}. {detalle}")
    return razones


def ensure_can_be_submitted(activities: list[Activity], *, area_has_person_in_charge: bool) -> None:
    razones = reasons_it_cannot_be_submitted(
        activities, area_has_person_in_charge=area_has_person_in_charge
    )
    if not razones:
        return
    raise ValidationError(EL_POA_DEL_AREA_NO_SE_PUEDE_ENVIAR + " ".join(razones))


def _enumerado(partes: list[str]) -> str:
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]
