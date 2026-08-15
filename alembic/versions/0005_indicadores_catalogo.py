from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0005_indicadores_catalogo"
down_revision = "0004_periodos"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0005_indicadores_catalogo.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS metas CASCADE")
    op.execute("DROP TABLE IF EXISTS lineas_base CASCADE")
    op.execute("DROP TABLE IF EXISTS indicador_criterios_seaes CASCADE")
    op.execute("DROP TABLE IF EXISTS indicador_instrumentos CASCADE")
    op.execute("DROP TABLE IF EXISTS indicadores CASCADE")
