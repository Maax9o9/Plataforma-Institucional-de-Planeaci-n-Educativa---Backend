from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0024_password_version"
down_revision = "0023_roles_cuatrimestres"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(
        op, Path(__file__).resolve().parents[2] / "bd/migrations/0024_password_version.sql"
    )


def downgrade() -> None:
    op.drop_column("usuarios", "password_version")
