"""El catalogo del POA pasa a tener un dueno: su POA."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0037_poa_por_ejercicio"
down_revision = "0036_catalogo_pse_administrable"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0037_poa_por_ejercicio.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # No hay vuelta atras automatica: deshacerla con mas de un POA cargado
    # exigiria decidir cual conservar y cual tirar, y tirar el catalogo de un
    # ano deja sin denominacion sus cedulas. Si hace falta volver, se restaura
    # un respaldo.
    raise NotImplementedError(
        "La 0037 no se revierte: con mas de un POA habria que elegir cual perder."
    )
