"""Cédula completa y entrega durable de recordatorios."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0026_cedula_recordatorios"
down_revision = "0025_notificaciones_entidad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op,
        Path(__file__).resolve().parents[2]
        / "bd/migrations/0026_cedula_completa_recordatorios.sql",
    )


def downgrade() -> None:
    # Fallará si existen tipos nuevos o porcentajes fuera del rango anterior; no borra registros.
    op.drop_index("uq_notificaciones_recordatorio_unico", table_name="notificaciones")
    op.execute(
        "ALTER TABLE notificaciones ALTER COLUMN tipo TYPE tipo_notificacion "
        "USING tipo::tipo_notificacion"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_notificaciones_recordatorio_unico "
        "ON notificaciones(usuario_id, tipo, entidad, entidad_id) "
        "WHERE tipo IN ('recordatorio_5d', 'recordatorio_3d', 'recordatorio_2d', 'recordatorio_1d')"
    )
    op.execute(
        "ALTER TABLE poa_cedula_indicadores ALTER COLUMN porcentaje_alcanzado TYPE numeric(7,4)"
    )
    op.drop_column("notificaciones", "correo_reservado_hasta")
    op.drop_constraint("ck_poa_tipo_estrategia", "poa_cedulas")
    op.drop_column("poa_cedulas", "firmantes")
    op.drop_column("poa_cedulas", "tipo_estrategia")
