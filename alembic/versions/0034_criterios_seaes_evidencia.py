"""Criterios SEAES de una evidencia."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0034_criterios_seaes_evidencia"
down_revision = "0033_unir_plantillas_correo"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0034_criterios_seaes_evidencia.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Se pierde a qué criterios respondía cada evidencia: no existía a dónde
    # guardarlo antes de esta migración. Es pérdida de datos documentada, no un
    # error.
    op.execute("DROP TABLE IF EXISTS evidencia_criterios")
