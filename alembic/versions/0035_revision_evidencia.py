"""Dictamen de Planeación sobre cada evidencia."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0035_revision_evidencia"
down_revision = "0034_criterios_seaes_evidencia"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0035_revision_evidencia.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Se pierde el dictamen de cada evidencia y su motivo: no existía a dónde
    # guardarlo antes de esta migración. Pérdida de datos documentada.
    op.execute("ALTER TABLE evidencias DROP CONSTRAINT IF EXISTS chk_evidencia_revision_completa")
    op.execute("ALTER TABLE evidencias DROP CONSTRAINT IF EXISTS chk_evidencia_rechazo_con_motivo")
    op.execute(
        "ALTER TABLE evidencias "
        "DROP COLUMN IF EXISTS comentario_revision, "
        "DROP COLUMN IF EXISTS revisado_en, "
        "DROP COLUMN IF EXISTS revisado_por, "
        "DROP COLUMN IF EXISTS estado_revision"
    )
    op.execute("DROP TYPE IF EXISTS estado_revision_evidencia")
