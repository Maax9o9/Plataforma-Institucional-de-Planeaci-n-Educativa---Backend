from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0014_catalogos_auxiliares"
down_revision = "0013_compatibilidad_api"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0014_catalogos_auxiliares.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("ALTER TABLE tipos_indicador DROP COLUMN IF EXISTS activo")
