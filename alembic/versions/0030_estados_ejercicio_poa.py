"""Estados y fecha limite del ejercicio POA."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0030_estados_ejercicio_poa"
down_revision = "0029_unir_cabezas_migracion"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0030_estados_ejercicio_poa.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_poa_ejercicios_estado")
    op.execute("ALTER TABLE poa_ejercicios DROP COLUMN IF EXISTS cerrado_en")
    op.execute("ALTER TABLE poa_ejercicios DROP COLUMN IF EXISTS comentario_revision")
    op.execute("ALTER TABLE poa_ejercicios DROP COLUMN IF EXISTS fecha_limite_formulacion")
    op.execute("ALTER TABLE poa_ejercicios DROP COLUMN IF EXISTS estado")
    op.execute("DROP TYPE IF EXISTS estado_ejercicio_poa")
    # No se revierten los valores agregados a entidad_flujo/estado_captura ni el
    # trigger: Postgres no permite quitar valores de un enum, y el trigger
    # actualizado sigue siendo compatible con las entidades anteriores.
