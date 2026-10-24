"""De donde salio una version del instrumento, y con que se mide cada accion."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import rechazar_si_hay_valores
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0039_origen_y_formula"
down_revision = "0038_arbol_del_pide"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0039_origen_y_formula.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Misma guarda que la 0038, en su version de columnas: esto no se lleva la
    # tabla sino dos columnas, asi que lo que hay que contar son los valores.
    # Una tabla llena de filas con la columna en NULL no pierde nada al bajar,
    # y negarse ahi seria negarse por costumbre. Con un solo origen o una sola
    # formula escritos, bajar los borra y no hay donde volver a ponerlos: la
    # formula vive en el PDF y el origen en la cabeza de quien cargo.
    conexion = op.get_bind()
    rechazar_si_hay_valores(conexion, "instrumento_versiones", "origen")
    rechazar_si_hay_valores(conexion, "nodos_estrategicos", "formula_indicador")

    op.execute("ALTER TABLE nodos_estrategicos DROP COLUMN IF EXISTS formula_indicador")
    op.execute("ALTER TABLE instrumento_versiones DROP COLUMN IF EXISTS origen")
