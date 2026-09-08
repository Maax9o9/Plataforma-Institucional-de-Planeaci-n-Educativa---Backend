from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0025_notificaciones_entidad"
down_revision = "0024_password_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op, Path(__file__).resolve().parents[2] / "bd/migrations/0025_notificaciones_entidad.sql"
    )


def downgrade() -> None:
    # PostgreSQL rechaza el downgrade si existen referencias que el enum antiguo no admite.
    # No se borran notificaciones para forzar la conversión.
    op.execute(
        "ALTER TABLE notificaciones ALTER COLUMN entidad TYPE entidad_flujo "
        "USING entidad::entidad_flujo"
    )
