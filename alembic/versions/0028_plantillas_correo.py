"""Plantillas editables; reúne las dos líneas de migración ya existentes."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0028_plantillas_correo"
down_revision = ("0026_cedula_recordatorios", "0027_revision_seguimiento_poa")
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op, Path(__file__).resolve().parents[2] / "bd/migrations/0028_plantillas_correo.sql"
    )


def downgrade() -> None:
    op.drop_table("plantillas_correo")
