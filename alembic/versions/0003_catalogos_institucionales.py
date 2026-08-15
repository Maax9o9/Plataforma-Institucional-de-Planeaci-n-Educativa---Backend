from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0003_catalogos_institucionales"
down_revision = "0002_identidad_y_seguridad"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0003_catalogos_institucionales.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS config_sistema CASCADE")
    op.execute("DROP TABLE IF EXISTS tipos_indicador CASCADE")
    op.execute("DROP TABLE IF EXISTS criterios_seaes CASCADE")
    op.execute("DROP TABLE IF EXISTS instrumentos CASCADE")
    op.execute("DROP TABLE IF EXISTS areas CASCADE")
