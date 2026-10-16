"""Flujo de revision del seguimiento cuatrimestral del POA."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0027_revision_seguimiento_poa"
down_revision = "0026_bitacora_usuario_nombre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op,
        Path(__file__).resolve().parents[2] / "bd/migrations/0027_revision_seguimiento_poa.sql",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_poa_cedula_seguimientos_estado;")
    op.execute("ALTER TABLE poa_cedula_seguimientos DROP COLUMN IF EXISTS comentario_revision;")
    op.execute("ALTER TABLE poa_cedula_seguimientos DROP COLUMN IF EXISTS estado;")
