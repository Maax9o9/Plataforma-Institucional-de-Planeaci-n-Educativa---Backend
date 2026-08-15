"""Endpoints de estructura anual del POA."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.core.security import get_current_user, require_roles

from ..application.dto import (
    CreateActivityCommand,
    CreateExerciseCommand,
    CreateObjectiveCommand,
    CreateProcessCommand,
    UpdateActivityCommand,
)
from ..application.use_cases.create_structure import (
    CreateActivity,
    CreateExercise,
    CreateObjective,
    CreateProcess,
    UpdateActivity,
)
from .dependencies import (
    get_create_activity_use_case,
    get_create_exercise_use_case,
    get_create_objective_use_case,
    get_create_process_use_case,
    get_update_activity_use_case,
)
from .schemas import (
    ActividadRespuesta,
    ActualizarActividadRequest,
    CrearActividadRequest,
    CrearEjercicioRequest,
    CrearObjetivoRequest,
    CrearProcesoRequest,
    EjercicioRespuesta,
    ObjetivoRespuesta,
    ProcesoRespuesta,
)

TAG = "Planeacion POA"
router = APIRouter(prefix="/poa", tags=[TAG])
PLANNING_ROLES = ("planeacion", "admin_sistema")
ACTIVITY_ROLES = ("planeacion", "admin_sistema", "responsable_area")


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
) -> EjercicioRespuesta:
    return EjercicioRespuesta.from_domain(
        await use_case.execute(CreateExerciseCommand(year=body.anio, actor_id=current_user.id))
    )


@router.post(
    "/procesos",
    response_model=ProcesoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear proceso POA",
)
async def create_process(
    body: CrearProcesoRequest,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CreateProcess = Depends(get_create_process_use_case),
) -> ProcesoRespuesta:
    return ProcesoRespuesta.from_domain(
        await use_case.execute(
            CreateProcessCommand(
                exercise_id=body.ejercicio_id,
                name=body.nombre,
                area_id=body.area_id,
                actor_id=current_user.id,
            )
        )
    )


@router.post(
    "/objetivos",
    response_model=ObjetivoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear objetivo POA",
)
async def create_objective(
    body: CrearObjetivoRequest,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CreateObjective = Depends(get_create_objective_use_case),
) -> ObjetivoRespuesta:
    return ObjetivoRespuesta.from_domain(
        await use_case.execute(
            CreateObjectiveCommand(
                process_id=body.proceso_id,
                poa_indicator=body.indicador_poa,
                objective=body.objetivo,
                actor_id=current_user.id,
            )
        )
    )


@router.post(
    "/actividades",
    response_model=ActividadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar actividad POA",
)
async def create_activity(
    body: CrearActividadRequest,
    current_user=Depends(require_roles(*ACTIVITY_ROLES)),
    use_case: CreateActivity = Depends(get_create_activity_use_case),
) -> ActividadRespuesta:
    return ActividadRespuesta.from_domain(
        await use_case.execute(
            CreateActivityCommand(
                objective_id=body.objetivo_id,
                description=body.descripcion,
                unit=body.unidad_medida,
                annual_goal=body.meta_anual,
                observations=body.observaciones,
                responsible_id=body.responsable_id,
                actor_id=current_user.id,
            )
        )
    )


@router.get(
    "/actividades", response_model=list[ActividadRespuesta], summary="Consultar actividades POA"
)
async def list_activities(
    request: Request,
    area_id: int | None = None,
    _current_user=Depends(get_current_user),
) -> list[ActividadRespuesta]:
    items = await request.app.state.poa_repository.list_activities(area_id=area_id)
    return [ActividadRespuesta.from_domain(item) for item in items]


@router.patch(
    "/actividades/{activity_id}",
    response_model=ActividadRespuesta,
    summary="Editar actividad POA",
)
async def update_activity(
    activity_id: int,
    body: ActualizarActividadRequest,
    current_user=Depends(require_roles(*ACTIVITY_ROLES)),
    use_case: UpdateActivity = Depends(get_update_activity_use_case),
) -> ActividadRespuesta:
    item = await use_case.execute(
        UpdateActivityCommand(
            activity_id=activity_id,
            description=body.descripcion,
            unit=body.unidad_medida,
            annual_goal=body.meta_anual,
            observations=body.observaciones,
            responsible_id=body.responsable_id,
            actor_id=current_user.id,
        )
    )
    return ActividadRespuesta.from_domain(item)
