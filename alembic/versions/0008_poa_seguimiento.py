from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0008_poa_seguimiento"
down_revision = "0007_poa_planeacion"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0008_poa_seguimiento.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poa_avance_criterios_seaes CASCADE")
    op.execute("DROP TABLE IF EXISTS poa_avances CASCADE")
