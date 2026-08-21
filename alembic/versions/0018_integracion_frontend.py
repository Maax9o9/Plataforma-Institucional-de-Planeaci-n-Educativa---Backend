from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0018_integracion_frontend"
down_revision = "0017_invitacion_contrasena"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0018_integracion_frontend.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("ALTER TABLE areas DROP CONSTRAINT IF EXISTS chk_areas_color")
    op.execute("ALTER TABLE areas DROP CONSTRAINT IF EXISTS chk_areas_tipo")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS color")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS tipo")
