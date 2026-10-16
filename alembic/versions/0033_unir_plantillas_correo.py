"""Une la cadena del POA con la de las plantillas de correo.

`0028_plantillas_correo` se escribio en develop mientras esta rama avanzaba de
`0028_criterio_seaes_actividad` a `0032_catalogo_unidades_medida`. Las dos
cuelgan de la misma base, asi que al fusionarlas la cadena vuelve a quedar con
dos cabezas y `alembic upgrade head` falla con "Multiple head revisions are
present": nadie puede levantar la base desde cero. Es el mismo choque que ya
resolvio `0029_unir_cabezas_migracion`, y se resuelve igual.

Esta revision no altera el esquema. Solo vuelve a unir las dos ramas para que la
cadena tenga una sola cabeza. No se reescribio el `down_revision` de ninguna de
las dos porque ambas ya estan aplicadas en bases existentes, y cambiarlo las
habria dejado inconsistentes.
"""

revision = "0033_unir_plantillas_correo"
down_revision = ("0032_catalogo_unidades_medida", "0028_plantillas_correo")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
