"""Actividad UPE y criterios SEAES múltiples por actividad."""

from pathlib import Path

from alembic import op

from app.shared.infrastructure.db.sql_loader import execute_sql_file

revision = "0031_actividad_upe_y_criterios"
down_revision = "0030_estados_ejercicio_poa"
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2]
    / "bd"
    / "migrations"
    / "0031_actividad_upe_y_criterios.sql"
)


def upgrade() -> None:
    execute_sql_file(op, SQL_FILE)


def downgrade() -> None:
    # Restaura la columna singular tomando el criterio de menor id de cada
    # actividad: si una actividad tenía más de uno, el downgrade sólo puede
    # conservar uno. Es pérdida de datos documentada, no un error.
    op.execute("ALTER TABLE poa_cedula_actividades ADD COLUMN criterio_seaes_id INTEGER")
    op.execute(
        """
        UPDATE poa_cedula_actividades AS actividad
        SET criterio_seaes_id = minimo.criterio_seaes_id
        FROM (
            SELECT DISTINCT ON (cedula_actividad_id)
                cedula_actividad_id, criterio_seaes_id
            FROM poa_cedula_actividad_criterios
            ORDER BY cedula_actividad_id, criterio_seaes_id
        ) AS minimo
        WHERE minimo.cedula_actividad_id = actividad.id
        """
    )
    op.execute(
        "ALTER TABLE poa_cedula_actividades "
        "ADD CONSTRAINT poa_cedula_actividades_criterio_seaes_id_fkey "
        "FOREIGN KEY (criterio_seaes_id) REFERENCES criterios_seaes(id)"
    )
    op.execute(
        "CREATE INDEX idx_poa_cedula_actividades_criterio "
        "ON poa_cedula_actividades(criterio_seaes_id)"
    )
    op.execute("ALTER TABLE poa_cedula_actividades DROP COLUMN actividad_upe")
    op.execute("DROP TABLE IF EXISTS poa_cedula_actividad_criterios")
