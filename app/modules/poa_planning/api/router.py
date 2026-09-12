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


@router.post(
    "/ejercicios",
    response_model=EjercicioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ejercicio anual POA",
)
async def create_exercise(
    body: CrearEjercicioRequest,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CreateExercise = Depends(get_create_exercise_use_case),
):
    item = await use_case.execute(
        CreateExerciseCommand(
            year=body.anio,
            actor_id=current_user.id,
            formulation_deadline=body.fecha_limite_formulacion,
        )
    )
    return EjercicioRespuesta.from_domain(item)


@router.get("/ejercicios", response_model=list[EjercicioRespuesta])
async def list_exercises(
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema", "capturista_poa")),
):
    items = await request.app.state.poa_repository.list_exercises()
    respuestas = []
    for item in items:
        cedulas = await request.app.state.poa_form_repository.list_forms(exercise_id=item.id)
        respuestas.append(EjercicioRespuesta.from_domain(item, total_cedulas=len(cedulas)))
    return respuestas


@router.post(
    "/ejercicios/{exercise_id}/enviar",
    response_model=EjercicioRespuesta,
    summary="Enviar el ejercicio POA a Rectoría",
)
async def send_exercise(
    exercise_id: int,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: SendExercise = Depends(get_send_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return EjercicioRespuesta.from_domain(item)


@router.post(
    "/ejercicios/{exercise_id}/aprobar",
    response_model=EjercicioRespuesta,
    summary="Rectoría aprueba el ejercicio POA",
)
async def approve_exercise(
    exercise_id: int,
    current_user=Depends(require_roles(*APPROVAL_ROLES)),
    use_case: ApproveExercise = Depends(get_approve_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return EjercicioRespuesta.from_domain(item)


@router.post(
    "/ejercicios/{exercise_id}/devolver",
    response_model=EjercicioRespuesta,
    summary="Rectoría devuelve el ejercicio POA con un motivo",
)
async def reject_exercise(
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
    return EjercicioRespuesta.from_domain(item)


@router.post(
    "/ejercicios/{exercise_id}/cerrar",
    response_model=EjercicioRespuesta,
    summary="Cerrar el ejercicio POA",
)
async def close_exercise(
    exercise_id: int,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CloseExercise = Depends(get_close_exercise_use_case),
):
    item = await use_case.execute(
        ExerciseActionCommand(exercise_id=exercise_id, actor=actor_from_user(current_user))
    )
    return EjercicioRespuesta.from_domain(item)
