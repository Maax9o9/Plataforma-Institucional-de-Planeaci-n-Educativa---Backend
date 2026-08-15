"""Consulta de notificaciones internas."""

from fastapi import APIRouter, Depends, Request

from app.core.security import get_current_user, require_roles

from ..application.reminders import GenerateReminders

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


def _response(item):
    return {
        "id": item.id,
        "tipo": item.notification_type,
        "mensaje": item.message,
        "entidad": item.entity,
        "entidad_id": item.entity_id,
        "leida": item.read,
        "enviada_por_correo": item.sent_by_email,
        "fecha": item.created_at,
    }


@router.get("", summary="Consultar notificaciones del usuario")
async def list_notifications(
    request: Request,
    no_leidas: bool = False,
    current_user=Depends(get_current_user),
):
    items = await request.app.state.notification_repository.list_for_user(
        current_user.id,
        unread_only=no_leidas,
    )
    return [_response(item) for item in items]


@router.post("/{notification_id}/leer", status_code=204, summary="Marcar notificacion como leida")
async def mark_notification_read(
    notification_id: int,
    request: Request,
    current_user=Depends(get_current_user),
):
    await request.app.state.notification_repository.mark_read(notification_id, current_user.id)


@router.post(
    "/recordatorios/generar",
    summary="Ejecutar generacion de recordatorios",
)
async def generate_reminders(
    request: Request,
    _current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    total = await GenerateReminders(
        request.app.state.period_repository,
        request.app.state.indicator_repository,
        request.app.state.notification_repository,
    ).execute()
    return {"generadas": total}
