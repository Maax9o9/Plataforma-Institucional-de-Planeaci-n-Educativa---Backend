from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0001_extensiones_y_enums"
down_revision = None
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0001_extensiones_y_enums.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    for enum_name in (
        "tipo_notificacion",
        "entidad_flujo",
        "tipo_evidencia",
        "semaforo",
        "estado_captura",
        "estado_periodo",
        "tipo_periodo",
        "periodicidad",
        "rol",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
