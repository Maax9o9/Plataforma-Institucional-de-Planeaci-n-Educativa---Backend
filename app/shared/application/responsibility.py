"""Politica compartida para asignar responsables operativos."""

from app.shared.domain.exceptions import ValidationError

OPERATIONAL_ROLES = {"responsable_area", "planeacion", "admin_sistema"}
GLOBAL_ROLES = {"planeacion", "admin_sistema"}


def ensure_operational_responsible(user, area_id: int) -> None:
    if user is None or not user.is_active:
        raise ValidationError("El responsable no existe o esta desactivado.")
    if not user.has_any_role(OPERATIONAL_ROLES):
        raise ValidationError(
            "El responsable debe tener rol Responsable de area, Planeacion o Administracion."
        )
    if not user.has_any_role(GLOBAL_ROLES) and user.area_id != area_id:
        raise ValidationError("El responsable debe pertenecer al area del registro.")
