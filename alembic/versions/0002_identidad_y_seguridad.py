from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0002_identidad_y_seguridad"
down_revision = "0001_extensiones_y_enums"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0002_identidad_y_seguridad.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bitacora_accesos CASCADE")
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS usuario_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS usuarios CASCADE")
