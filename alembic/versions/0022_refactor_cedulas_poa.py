from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0022_refactor_cedulas_poa"
down_revision = "0021_pendientes_frontend"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0022_refactor_cedulas_poa.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poa_cedula_emisiones")
    op.execute("DROP TABLE IF EXISTS poa_cedula_seguimientos")
    op.execute("DROP TABLE IF EXISTS poa_cedula_actividades")
    op.execute("DROP TABLE IF EXISTS poa_cedula_indicadores")
    op.execute("DROP TABLE IF EXISTS poa_cedulas")
    op.execute("DROP TABLE IF EXISTS poa_catalogo_actividades")
    op.execute("DROP TABLE IF EXISTS poa_catalogo_indicadores")
    op.execute("DROP TABLE IF EXISTS poa_catalogo_estrategias")
    op.execute("DROP TABLE IF EXISTS poa_catalogo_objetivos")
