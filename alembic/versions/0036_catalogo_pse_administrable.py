"""El catálogo del PSE deja de ser inmutable."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0036_catalogo_pse_administrable"
down_revision = "0035_revision_evidencia"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0036_catalogo_pse_administrable.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Vuelve a atar el número de objetivo a 1..6. Si para entonces existe un
    # objetivo fuera de ese rango, el CHECK no se puede crear y el downgrade
    # falla: es correcto, borrar ese objetivo en silencio sería peor.
    op.execute("ALTER TABLE poa_catalogo_objetivos DROP CONSTRAINT IF EXISTS chk_poa_objetivo_numero")
    op.execute(
        "ALTER TABLE poa_catalogo_objetivos ADD CONSTRAINT chk_poa_objetivo_numero "
        "CHECK (numero >= 1 AND numero <= 6)"
    )
