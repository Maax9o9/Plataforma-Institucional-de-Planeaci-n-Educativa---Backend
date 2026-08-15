from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0009_evidencias_y_flujo"
down_revision = "0008_poa_seguimiento"
branch_labels = None
depends_on = None
SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0009_evidencias_y_flujo.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_cambios_estado_valida_entidad ON cambios_estado")
    op.execute("DROP TRIGGER IF EXISTS trg_evidencia_vinculos_valida_entidad ON evidencia_vinculos")
    op.execute("DROP FUNCTION IF EXISTS fn_validar_entidad_flujo()")
    op.execute("DROP TABLE IF EXISTS cambios_estado CASCADE")
    op.execute("DROP TABLE IF EXISTS evidencia_versiones CASCADE")
    op.execute("DROP TABLE IF EXISTS evidencia_vinculos CASCADE")
    op.execute("DROP TABLE IF EXISTS evidencias CASCADE")
