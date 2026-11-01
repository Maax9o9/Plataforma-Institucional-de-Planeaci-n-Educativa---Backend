from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
    cabe_en_el_entero_de_la_base,
)
from app.shared.domain.captured_text import recortado_sin_invisibles
from app.shared.domain.exceptions import InvalidStateError, ValidationError

MESES_DEL_EJERCICIO = tuple(range(1, 13))

DECIMALES_DE_LA_META = 4
ENTEROS_DE_LA_META = 14
META_MAS_ALTA_QUE_CABE = Decimal(10) ** ENTEROS_DE_LA_META - Decimal(1).scaleb(
    -DECIMALES_DE_LA_META
)

NIVEL_DE_LA_ACTIVIDAD = NodeKind.ACCION


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
    if not activity.evaluation_method:
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


def ensure_can_be_submitted(activities: list[Activity], *, area_has_person_in_charge: bool) -> None:
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
    if not razones:
        return
    raise ValidationError("El POA del área no se puede enviar. " + " ".join(razones))


def _enumerado(partes: list[str]) -> str:
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]
