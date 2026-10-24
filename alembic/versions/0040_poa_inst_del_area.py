from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import rechazar_si_hay_filas
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0040_poa_inst_del_area"
down_revision = "0039_origen_y_formula"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0040_poa_inst_del_area.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    rechazar_si_hay_filas(
        op.get_bind(),
        "poa_inst_areas",
        "poa_inst_actividades",
        "poa_inst_programacion_mensual",
    )
    op.execute("DROP TABLE IF EXISTS poa_inst_programacion_mensual")
    op.execute("DROP TABLE IF EXISTS poa_inst_actividades")
    op.execute("DROP TABLE IF EXISTS poa_inst_areas")
