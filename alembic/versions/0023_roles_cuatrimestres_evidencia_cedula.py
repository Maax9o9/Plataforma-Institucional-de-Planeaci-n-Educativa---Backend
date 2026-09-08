from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0023_roles_cuatrimestres"
down_revision = "0022_refactor_cedulas_poa"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0023_roles_cuatrimestres_evidencia_cedula.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poa_cedula_cuatrimestres")
    op.execute("ALTER TABLE poa_cedula_seguimientos DROP COLUMN IF EXISTS alcance")
    op.execute("ALTER TABLE poa_cedula_seguimientos DROP COLUMN IF EXISTS progreso")
