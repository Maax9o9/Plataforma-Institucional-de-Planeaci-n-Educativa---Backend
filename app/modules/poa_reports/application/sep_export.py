"""Arma el formato de la SEP con lo que la plataforma tiene capturado."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.modules.poa_planning.application.access_control import can_edit_structure
from app.modules.poa_planning.domain.ports.cedula_repository import PoaFormRepository
from app.modules.poa_planning.domain.ports.repositories import PoaRepository
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from .sep_format import (
    ActividadDelFormato,
    CedulaDelFormato,
    IndicadorDelFormato,
    con_clave,
    llenar_formato,
)

#: La plantilla oficial, en blanco. Se versiona con el código porque es el
#: entregable: sin ella no hay forma de producir el formato que pide la SEP.
PAQUETE_PLANTILLA = "app.modules.poa_reports.resources"
ARCHIVO_PLANTILLA = "formato-poa-sep.xlsm"

MEDIA_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"


@lru_cache(maxsize=1)
def plantilla() -> bytes:
    """Son 4,6 MiB que no cambian durante la vida del proceso: leerlos del
    disco en cada descarga sería un viaje de ida y vuelta por nada."""
    return resources.files(PAQUETE_PLANTILLA).joinpath(ARCHIVO_PLANTILLA).read_bytes()


class ExportarFormatoSep:
    """El POA de un ejercicio, en el archivo que se entrega.

    Lee las **cédulas vivas** y no la emisión inmutable, que es lo que el
    diseño original prefería. El motivo es que hoy ninguna cédula se puede
    emitir —el backend exige dos firmantes y la interfaz todavía no los
    captura—, así que exportar desde las emisiones produciría un archivo vacío.
    El costo es que el archivo refleja lo capturado en el momento de pedirlo, y
    por eso el nombre lleva la fecha. Cuando la emisión funcione, esta clase
    gana una segunda fuente; la que arma el archivo no cambia.
    """

    def __init__(
        self,
        forms: PoaFormRepository,
        exercises: PoaRepository,
        areas: AreaRepository,
    ) -> None:
        self.forms = forms
        self.exercises = exercises
        self.areas = areas

    async def execute(self, *, exercise_id: int, actor: ActorContext) -> tuple[bytes, list[str]]:
        # Rectoría también lo descarga, y no es un permiso de más: **este
        # archivo es lo que se le manda para validar que el POA de la
        # universidad está bien hecho**. Negárselo obligaría a que Planeación
        # se lo reenviara por correo, que es justo el trabajo paralelo que la
        # plataforma viene a quitar.
        if not await can_edit_structure(actor, self.areas) and not actor.has_any_role("rectoria"):
            raise ForbiddenError(
                "Sólo Planeación y Rectoría pueden generar el formato de la SEP.",
                details={"reason": "POA_PLANNING_REQUIRED"},
            )
        exercise = await self.exercises.get_exercise(exercise_id)
        if exercise is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")

        # Las cuatro consultas al catálogo salen del POA del que cuelga el
        # ejercicio que se exporta: el formato de un año tiene que decir lo que
        # decía *ese* POA, y la clave `1.1.1` puede existir en varios con
        # textos distintos.
        #
        # Aquí basta un POA -y no el conjunto distinto, como en el tablero y en
        # los reportes- porque la exportación está acotada a un ejercicio. Y
        # para que eso se pueda comprobar leyendo esta función, las cuatro usan
        # esta misma local y ninguna vuelve a `form.catalog_id`: son iguales
        # -lo garantizan `uq_poa_ejercicio_catalogo` y la foránea compuesta de
        # la cédula-, pero leerlo de un solo sitio no obliga a saberse el
        # esquema para creerle al párrafo de arriba.
        #
        # Los tres primeros se piden antes del bucle porque no habría cédulas
        # de las que sacar el dato si el ejercicio estuviera vacío.
        catalogo_id = exercise.catalog_id
        objetivos = {
            item.number: item for item in await self.forms.list_objectives(catalog_id=catalogo_id)
        }
        acciones = {
            item.key: item
            for item in await self.forms.list_activity_catalog(catalog_id=catalogo_id)
        }
        indicadores = {
            item.key: item for item in await self.forms.list_indicators(catalog_id=catalogo_id)
        }

        cedulas: list[CedulaDelFormato] = []
        for form in await self.forms.list_forms(exercise_id=exercise_id):
            detalle = await self.forms.get_detail(form.id)
            if detalle is None:
                continue
            estrategia = await self.forms.get_strategy(catalogo_id, form.strategy_key)
            objetivo = objetivos.get(form.objective_number)
            cedulas.append(
                CedulaDelFormato(
                    objective_number=form.objective_number,
                    strategy_key=form.strategy_key,
                    strategy_denomination=(
                        estrategia.denomination if estrategia is not None else form.strategy_key
                    ),
                    strategy_type=form.strategy_type,
                    responsible_area=await self._nombre_de_area(form.responsible_area_id) or "",
                    objective_denomination=objetivo.denomination if objetivo is not None else "",
                    scope_and_socioeconomic_effect=form.scope_and_socioeconomic_effect,
                    signatories=tuple(
                        (firmante.name, firmante.position) for firmante in form.signatories
                    ),
                    indicators=tuple(
                        _indicador(item, indicadores.get(item.indicator_key))
                        for item in detalle.indicators
                    ),
                    activities=tuple(
                        [
                            await self._actividad(item, detalle, acciones.get(item.activity_key))
                            for item in detalle.activities
                        ]
                    ),
                )
            )

        archivo, incidencias = llenar_formato(plantilla(), cedulas, anio=exercise.year)
        if not cedulas:
            incidencias.insert(
                0, f"El ejercicio {exercise.year} no tiene cédulas: el formato va en blanco."
            )
        return archivo, incidencias

    async def _nombre_de_area(self, area_id: int | None) -> str | None:
        if area_id is None:
            return None
        area = await self.areas.get_by_id(area_id)
        return area.name if area is not None else None

    async def _actividad(self, item, detalle, catalogo) -> ActividadDelFormato:
        seguimientos = {
            seguimiento.quarter: seguimiento
            for seguimiento in detalle.follow_ups
            if seguimiento.form_activity_id == item.id
        }
        return ActividadDelFormato(
            key=item.activity_key,
            description=catalogo.description if catalogo is not None else "",
            unit=item.unit,
            annual_goal=item.annual_goal,
            executing_area=await self._nombre_de_area(item.executing_area_id),
            # La justificación del formato es una sola por actividad y el
            # sistema la guarda por cuatrimestre: se unen las que haya, en
            # orden, para no perder ninguna.
            deviation_justification=_justificaciones(seguimientos),
            scheduled={q: s.scheduled for q, s in seguimientos.items()},
            achieved={q: s.achieved for q, s in seguimientos.items()},
        )


def _indicador(item, catalogo) -> IndicadorDelFormato:
    return IndicadorDelFormato(
        name=con_clave(item.indicator_key, catalogo.name if catalogo is not None else ""),
        formula=catalogo.formula if catalogo is not None else "",
        unit=catalogo.unit if catalogo is not None else "",
        institutional_goal=item.institutional_goal,
        baseline_year=item.baseline_year,
        baseline_value=item.baseline_value,
        current_percentage=item.current_percentage,
        target_value=item.target_value,
        target_percentage=item.target_percentage,
        achieved_total=item.total_achieved,
        achieved_percentage=item.achieved_percentage,
    )


def _justificaciones(seguimientos: dict) -> str | None:
    partes = [
        f"{q}° cuatrimestre: {seguimientos[q].deviation_justification.strip()}"
        for q in sorted(seguimientos)
        if (seguimientos[q].deviation_justification or "").strip()
    ]
    return "\n".join(partes) if partes else None
