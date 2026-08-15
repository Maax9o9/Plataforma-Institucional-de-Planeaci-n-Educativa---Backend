from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0007_poa_planeacion"
down_revision = "0006_indicadores_captura"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0007_poa_planeacion.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poa_actividades CASCADE")
    op.execute("DROP TABLE IF EXISTS poa_objetivos CASCADE")
    op.execute("DROP TABLE IF EXISTS poa_procesos CASCADE")
    op.execute("DROP TABLE IF EXISTS poa_ejercicios CASCADE")
