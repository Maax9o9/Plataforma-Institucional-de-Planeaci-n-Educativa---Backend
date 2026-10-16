"""Instantanea del nombre del autor en la bitacora."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0026_bitacora_usuario_nombre"
down_revision = "0025_notificaciones_entidad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op,
        Path(__file__).resolve().parents[2] / "bd/migrations/0026_bitacora_usuario_nombre.sql",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bitacora DROP COLUMN IF EXISTS usuario_nombre;")
