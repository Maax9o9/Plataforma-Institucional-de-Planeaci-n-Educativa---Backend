from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0012_reportes_y_dashboards"
down_revision = "0011_bitacora"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0012_reportes_y_dashboards.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_avance_institucional_indicadores")
    op.execute("DROP TABLE IF EXISTS reportes_generados CASCADE")
