"""El titulo de los avisos dirigidos a un area."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import rechazar_si_hay_valores
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0042_aviso_del_area"
down_revision = "0041_apertura_del_poa_inst"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0042_aviso_del_area.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Bajar la migracion borra los titulos ya capturados y no hay de donde
    # volver a sacarlos: el mensaje no los contiene.
    rechazar_si_hay_valores(op.get_bind(), "notificaciones", "titulo")
    op.drop_column("notificaciones", "titulo")
