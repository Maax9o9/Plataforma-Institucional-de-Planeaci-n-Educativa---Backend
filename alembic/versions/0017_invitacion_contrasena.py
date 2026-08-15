from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0017_invitacion_contrasena"
down_revision = "0016_mv_avance_poa"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0017_invitacion_contrasena.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tokens_configuracion_contrasena")
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS requiere_configurar_contrasena")
