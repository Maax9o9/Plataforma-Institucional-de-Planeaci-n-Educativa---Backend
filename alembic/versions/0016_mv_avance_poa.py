from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0016_mv_avance_poa"
down_revision = "0015_notificaciones_idempotencia"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0016_mv_avance_poa.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_avance_institucional_poa")
