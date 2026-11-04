"""El comunicado es un registro propio y la notificacion es su entrega."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.downgrade_guard import (
    rechazar_si_hay_filas,
    rechazar_si_hay_valores,
)
from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0043_avisos_utiles"
down_revision = "0042_aviso_del_area"
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[2] / "bd" / "migrations" / "0043_avisos_utiles.sql"


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Bajar la migracion borra los comunicados redactados -con su destino, su
    # vigencia y sus adjuntos- y, con `notificaciones.aviso_id`, el unico dato
    # por el que las entregas de un mismo comunicado se agrupan. Nada de eso se
    # puede volver a derivar: el mensaje de la entrega no dice de que
    # comunicado venia.
    conexion = op.get_bind()
    rechazar_si_hay_valores(conexion, "notificaciones", "aviso_id")
    rechazar_si_hay_filas(conexion, "avisos", "aviso_adjuntos")
    op.drop_index("idx_notificaciones_aviso", table_name="notificaciones")
    op.drop_constraint("fk_notificacion_aviso", "notificaciones", type_="foreignkey")
    op.drop_column("notificaciones", "aviso_id")
    op.execute("DROP TABLE IF EXISTS aviso_adjuntos")
    op.execute("DROP TABLE IF EXISTS avisos")
