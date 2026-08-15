from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0004_periodos"
down_revision = "0003_catalogos_institucionales"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0004_periodos.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS periodos CASCADE")
