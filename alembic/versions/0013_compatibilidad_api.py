from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0013_compatibilidad_api"
down_revision = "0012_reportes_y_dashboards"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0013_compatibilidad_api.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_refresh_tokens_session")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS session_id")
    op.execute("ALTER TABLE bitacora DROP COLUMN IF EXISTS evento")
    op.execute("DROP INDEX IF EXISTS uq_areas_codigo")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS parent_id")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS codigo")
    op.execute("DROP INDEX IF EXISTS uq_instrumentos_codigo")
    op.execute("ALTER TABLE instrumentos DROP COLUMN IF EXISTS descripcion")
    op.execute("ALTER TABLE instrumentos DROP COLUMN IF EXISTS codigo")
