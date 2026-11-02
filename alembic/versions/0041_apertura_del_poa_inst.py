from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import rechazar_si_hay_filas
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0041_apertura_del_poa_inst"
down_revision = "0040_poa_inst_del_area"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0041_apertura_del_poa_inst.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    rechazar_si_hay_filas(op.get_bind(), "poa_inst_aperturas")
    op.execute("DROP TABLE IF EXISTS poa_inst_aperturas")
