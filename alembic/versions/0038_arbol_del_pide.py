"""El instrumento deja de ser un nombre y pasa a tener su arbol."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0038_arbol_del_pide"
down_revision = "0037_poa_por_ejercicio"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0038_arbol_del_pide.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Se pierden las versiones del instrumento, su arbol y a que nodo respondia
    # cada indicador: nada de eso existia antes de esta migracion. Es perdida de
    # datos documentada, no un error. El arbol del PIDE se puede volver a cargar
    # de su semilla, pero lo que Planeacion hubiera editado o retirado a mano
    # no. Sin CASCADE a proposito: si algo mas cuelga ya de estas tablas, el
    # downgrade tiene que fallar y no llevarselo por delante.
    op.execute("ALTER TABLE indicadores DROP COLUMN IF EXISTS nodo_id")
    op.execute("DROP TABLE IF EXISTS nodos_estrategicos")
    op.execute("DROP TABLE IF EXISTS instrumento_versiones")
