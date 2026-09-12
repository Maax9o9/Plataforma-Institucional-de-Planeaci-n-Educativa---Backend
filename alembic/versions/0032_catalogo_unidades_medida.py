"""Catalogo de unidades de medida de las actividades del POA."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0032_catalogo_unidades_medida"
down_revision = "0031_actividad_upe_y_criterios"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0032_catalogo_unidades_medida.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS unidades_medida")
