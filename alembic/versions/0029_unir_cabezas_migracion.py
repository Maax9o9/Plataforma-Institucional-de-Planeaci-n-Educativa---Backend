"""Une las dos cabezas de migracion que quedaron tras fusionar ramas paralelas.

`0026_bitacora_usuario_nombre` y `0026_cedula_recordatorios` se escribieron en
ramas distintas y ambas colgaron de `0025_notificaciones_entidad`, asi que al
fusionarlas en develop la cadena quedo con dos cabezas y `alembic upgrade head`
fallaba con "Multiple head revisions are present": nadie podia levantar la base
desde cero.

Esta revision no altera el esquema. Solo vuelve a unir las dos ramas para que la
cadena tenga una sola cabeza otra vez. No se reescribio el `down_revision` de
ninguna de las dos porque ambas ya estaban aplicadas en bases existentes, y
cambiarlo las habria dejado inconsistentes.
"""

revision = "0029_unir_cabezas_migracion"
down_revision = ("0028_criterio_seaes_actividad", "0026_cedula_recordatorios")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
