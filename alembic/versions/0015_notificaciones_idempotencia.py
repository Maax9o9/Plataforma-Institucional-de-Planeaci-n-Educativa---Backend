from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0015_notificaciones_idempotencia"
down_revision = "0014_catalogos_auxiliares"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0015_notificaciones_idempotencia.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_notificaciones_evento_idempotente")
    op.execute("ALTER TABLE notificaciones DROP COLUMN IF EXISTS origen_evento_id")
