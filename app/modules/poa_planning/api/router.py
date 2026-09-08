"""Ejercicios anuales del único flujo de cédulas POA."""

from fastapi import APIRouter, Depends, Request, status

from app.core.security import require_roles

from ..application.dto import CreateExerciseCommand
from ..application.use_cases.create_structure import CreateExercise
from .dependencies import get_create_exercise_use_case
from .schemas import CrearEjercicioRequest, EjercicioRespuesta

router = APIRouter(prefix="/poa", tags=["Cédulas POA"])


@router.post(
    "/ejercicios",
    response_model=EjercicioRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ejercicio anual POA",
)
async def create_exercise(
    body: CrearEjercicioRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: CreateExercise = Depends(get_create_exercise_use_case),
):
    item = await use_case.execute(CreateExerciseCommand(year=body.anio, actor_id=current_user.id))
    return EjercicioRespuesta.from_domain(item)


@router.get("/ejercicios", response_model=list[EjercicioRespuesta])
async def list_exercises(
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema", "capturista_poa")),
):
    return [
        EjercicioRespuesta.from_domain(item)
        for item in await request.app.state.poa_repository.list_exercises()
    ]
