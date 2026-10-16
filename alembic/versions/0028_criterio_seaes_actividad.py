"""Criterio SEAES por actividad del POA."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0028_criterio_seaes_actividad"
down_revision = "0027_revision_seguimiento_poa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op,
        Path(__file__).resolve().parents[2] / "bd/migrations/0028_criterio_seaes_actividad.sql",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_poa_cedula_actividades_criterio;")
    op.execute("ALTER TABLE poa_cedula_actividades DROP COLUMN IF EXISTS criterio_seaes_id;")
