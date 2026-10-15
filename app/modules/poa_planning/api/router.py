"""Ejercicios anuales del único flujo de cédulas POA."""

from fastapi import APIRouter, Depends, Request, status

from app.core.authorization import actor_from_user
from app.core.security import require_roles

from ..application.access_control import APPROVAL_ROLES
from ..application.dto import CreateExerciseCommand
from ..application.use_cases.create_structure import CreateExercise
from ..application.use_cases.manage_exercise import (
    ApproveExercise,
    CloseExercise,
    ExerciseActionCommand,
    RejectExercise,
    SendExercise,
)
from ..domain.entities import PoaExercise
from .dependencies import (
    get_approve_exercise_use_case,
    get_close_exercise_use_case,
    get_create_exercise_use_case,
    get_reject_exercise_use_case,
    get_send_exercise_use_case,
)
from .schemas import CrearEjercicioRequest, DevolverEjercicioRequest, EjercicioRespuesta

router = APIRouter(prefix="/poa", tags=["Cédulas POA"])

#: Quien arma y administra el ejercicio: Planeación.
PLANNING_ROLES = ("planeacion", "planeacion_admin", "admin_sistema")
#: Quien lo aprueba o lo devuelve: sólo Rectoría, sin atajos administrativos.
#: Fuente de verdad en `application/access_control.py` -la comparte con los
#: casos de uso `ApproveExercise`/`RejectExercise`, que la vuelven a exigir
#: como defensa en profundidad si algún día algo llega a ellos sin pasar por
#: esta puerta HTTP-.


async def _nombres_de_poa(request: Request) -> dict[int, str]:
    """Los nombres de los POA, por id, para ponerlos en la respuesta del ejercicio.

    El ejercicio guarda el `catalogo_id`, pero la pantalla muestra «POA 2026»: un
    id no se le muestra a nadie. Se piden todos juntos porque son un puñado y así
    el listado resuelve cada ejercicio sin una consulta por fila.
    """
    catalogos = await request.app.state.poa_form_repository.list_catalogs()
    return {catalogo.id: catalogo.name for catalogo in catalogos}


async def _respuesta(request: Request, item: PoaExercise) -> EjercicioRespuesta:
    """La respuesta de un solo ejercicio: la comparten la alta y las cuatro
    acciones del ciclo, para que ninguna conteste sin el nombre de su POA."""
    nombres = await _nombres_de_poa(request)
    return EjercicioRespuesta.from_domain(item, catalogo_nombre=nombres.get(item.catalog_id))


@router.post(
    "/ejercicios",
    response_model=EjercicioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ejercicio anual POA",
)
async def create_exercise(
    request: Request,
    body: CrearEjercicioRequest,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CreateExercise = Depends(get_create_exercise_use_case),
):
    item = await use_case.execute(
        CreateExerciseCommand(
            year=body.anio,
            catalog_id=body.catalogo_id,
            actor_id=current_user.id,
            formulation_deadline=body.fecha_limite_formulacion,
        )
    )
    return await _respuesta(request, item)


@router.get("/ejercicios", response_model=list[EjercicioRespuesta])
async def list_exercises(
    request: Request,
    # Rectoría entra a leer: es quien aprueba o devuelve el ejercicio, y sin
    # el listado no tenía forma de llegar hasta él. Sólo lectura: aprobar y
    # devolver siguen gobernados por APPROVAL_ROLES.
    current_user=Depends(
        require_roles("planeacion", "admin_sistema", "capturista_poa", "rectoria")
    ),
):
    items = await request.app.state.poa_repository.list_exercises()
    nombres = await _nombres_de_poa(request)
    respuestas = []
    for item in items:
        cedulas = await request.app.state.poa_form_repository.list_forms(exercise_id=item.id)
        respuestas.append(
            EjercicioRespuesta.from_domain(
                item, catalogo_nombre=nombres.get(item.catalog_id), total_cedulas=len(cedulas)
            )
        )
    return respuestas


@router.post(
    "/ejercicios/{exercise_id}/enviar",
    response_model=EjercicioRespuesta,
    summary="Enviar el ejercicio POA a Rectoría",
)
async def send_exercise(
    request: Request,
    exercise_id: int,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: SendExercise = Depends(get_send_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return await _respuesta(request, item)


@router.post(
    "/ejercicios/{exercise_id}/aprobar",
    response_model=EjercicioRespuesta,
    summary="Rectoría aprueba el ejercicio POA",
)
async def approve_exercise(
    request: Request,
    exercise_id: int,
    current_user=Depends(require_roles(*APPROVAL_ROLES)),
    use_case: ApproveExercise = Depends(get_approve_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return await _respuesta(request, item)


@router.post(
    "/ejercicios/{exercise_id}/devolver",
    response_model=EjercicioRespuesta,
    summary="Rectoría devuelve el ejercicio POA con un motivo",
)
async def reject_exercise(
    request: Request,
    exercise_id: int,
    body: DevolverEjercicioRequest,
    current_user=Depends(require_roles(*APPROVAL_ROLES)),
    use_case: RejectExercise = Depends(get_reject_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(
            exercise_id=exercise_id,
            actor=actor_from_user(current_user),
            comment=body.comentario,
        )
    )
    return await _respuesta(request, item)


@router.post(
    "/ejercicios/{exercise_id}/cerrar",
    response_model=EjercicioRespuesta,
    summary="Cerrar el ejercicio POA",
)
async def close_exercise(
    request: Request,
    exercise_id: int,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CloseExercise = Depends(get_close_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return await _respuesta(request, item)
