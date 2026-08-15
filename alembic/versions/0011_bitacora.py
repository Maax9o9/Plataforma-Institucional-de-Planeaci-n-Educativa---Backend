from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0011_bitacora"
down_revision = "0010_notificaciones"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0011_bitacora.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bitacora_inmutable ON bitacora")
    op.execute("DROP FUNCTION IF EXISTS fn_bitacora_inmutable()")
    op.execute("DROP TABLE IF EXISTS bitacora CASCADE")
