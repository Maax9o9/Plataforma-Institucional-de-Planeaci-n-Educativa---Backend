"""Políticas de cédulas compartidas por aplicación, consultas y evidencias."""

from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError

PLANNING_AREA_NAME = "Dirección de Planeación Educativa"

#: Quien aprueba o devuelve el ejercicio POA: sólo Rectoría, sin atajos
#: administrativos.
#:
#: Este paso existe para que Planeación no apruebe su propio trabajo -es
#: separación de responsabilidades, no un trámite-. `admin_sistema` y
#: `planeacion_admin` no entran aquí a propósito: son roles de soporte de
#: Planeación (por eso `ActorContext.is_planning` los incluye), así que
#: admitirlos aquí dejaría aprobar a una cuenta de Planeación y el control
#: quedaría decorativo. Si algún día Rectoría necesita delegar la
#: aprobación a alguien más, que sea un rol propio de Rectoría, no el
#: comodín de sistema. No "arreglar" agregando esos roles de vuelta.
#:
#: Única fuente de verdad: la usan tanto el router (para bloquear la
#: petición HTTP) como los casos de uso `ApproveExercise`/`RejectExercise`
#: (para no depender únicamente de esa puerta de entrada).
APPROVAL_ROLES = ("rectoria",)


def can_approve_exercise(actor: ActorContext) -> bool:
    return actor.has_any_role(*APPROVAL_ROLES)


def ensure_planning(actor: ActorContext) -> None:
    if not actor.is_planning:
        raise ForbiddenError(
            "Esta operación requiere permisos de Planeación.",
            details={"reason": "POA_PLANNING_REQUIRED"},
        )


def can_capture_activity(actor: ActorContext, executing_area_id: int | None) -> bool:
    return actor.is_planning or (
        actor.has_any_role("capturista_poa")
        and actor.area_id is not None
        and actor.area_id == executing_area_id
    )


async def can_edit_structure(actor: ActorContext, areas: AreaRepository) -> bool:
    if actor.is_planning:
        return True
    if actor.has_any_role("capturista_poa") and actor.area_id is not None:
        area = await areas.get_by_id(actor.area_id)
        if area and area.is_active and area.name.casefold() == PLANNING_AREA_NAME.casefold():
            return True
    return False


async def ensure_structure_access(actor: ActorContext, areas: AreaRepository) -> None:
    if await can_edit_structure(actor, areas):
        return
    raise ForbiddenError(
        "Sólo Planeación puede capturar la estructura de la cédula.",
        details={"reason": "POA_PLANNING_REQUIRED"},
    )
