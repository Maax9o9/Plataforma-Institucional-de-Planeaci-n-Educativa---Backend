"""La actividad del POA del area lleva su monto solicitado."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import rechazar_si_hay_valores
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0044_monto_de_la_actividad"
down_revision = "0043_avisos_utiles"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0044_monto_de_la_actividad.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Bajar la migracion borra el presupuesto capturado por actividad y no hay
    # de donde volver a derivarlo: el monto no se calcula de la meta ni de los
    # meses.
    conexion = op.get_bind()
    rechazar_si_hay_valores(conexion, "poa_inst_actividades", "monto_solicitado")
    op.drop_constraint(
        "ck_poa_inst_actividad_monto_no_negativo",
        "poa_inst_actividades",
        type_="check",
    )
    op.drop_column("poa_inst_actividades", "monto_solicitado")
