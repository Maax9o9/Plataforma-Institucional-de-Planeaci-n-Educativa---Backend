from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0021_pendientes_frontend"
down_revision = "0020_version_indicadores"
branch_labels = None
depends_on = None
SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0021_pendientes_integracion_frontend.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_indicadores_actualizado_id")
    op.execute("DROP INDEX IF EXISTS idx_capturas_actualizado_id")
    op.execute("ALTER TABLE capturas DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE periodos DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE tipos_indicador DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE criterios_seaes DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE instrumentos DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS ultimo_acceso")
