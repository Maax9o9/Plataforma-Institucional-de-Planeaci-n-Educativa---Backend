"""Bajar una migración que se lleva datos: negarse en vez de elegir qué perder."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

#: Las tablas y columnas se nombran en el código de la migración, nunca llegan
#: de fuera; esto es para que siga siendo cierto si alguien las parametriza.
_NOMBRE = re.compile(r"^[a-z_][a-z0-9_]*$")


def rechazar_si_hay_filas(conexion: Connection, *tablas: str) -> None:
    """Para el `downgrade` si alguna de esas tablas tiene filas.

    El precedente es la 0037, que se niega a revertirse porque deshacerla con
    más de un POA cargado exigiría decidir cuál conservar. Aquí la pregunta es
    la misma con otra forma: la tabla que la migración creó no existía antes,
    así que bajarla borra todo lo que se haya cargado o editado a mano y no
    deja dónde volver a ponerlo. Mientras esté vacía no hay nada que perder y
    el `downgrade` sigue siendo útil -una instalación recién migrada puede
    volver atrás-; en cuanto hay una fila, se restaura un respaldo.

    Dice cuántas filas y en qué tabla: quien baja una migración a mano necesita
    saber qué iba a perder, no que «no se puede».
    """
    pobladas = []
    for tabla in tablas:
        if not _NOMBRE.match(tabla):
            raise ValueError(f"«{tabla}» no es un nombre de tabla.")
        cuantas = conexion.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one()
        if cuantas:
            pobladas.append(f"{tabla} ({cuantas})")
    if not pobladas:
        return
    raise RuntimeError(
        "Esta migracion no se revierte con datos cargados: "
        + ", ".join(pobladas)
        + ". Bajarla los borra y no hay donde volver a ponerlos; si hace falta "
        "volver, se restaura un respaldo."
    )


def rechazar_si_hay_valores(conexion: Connection, tabla: str, *columnas: str) -> None:
    """Lo mismo para una migración que sólo agrega columnas.

    Bajarla no se lleva la tabla, sólo esas columnas, así que lo que hay que
    contar no son las filas sino los valores: una tabla llena de filas sin nada
    escrito en la columna nueva no pierde nada al bajar, y negarse ahí sería
    negarse por costumbre.
    """
    if not _NOMBRE.match(tabla):
        raise ValueError(f"«{tabla}» no es un nombre de tabla.")
    con_valor = []
    for columna in columnas:
        if not _NOMBRE.match(columna):
            raise ValueError(f"«{columna}» no es un nombre de columna.")
        cuantos = conexion.execute(text(f"SELECT count({columna}) FROM {tabla}")).scalar_one()
        if cuantos:
            con_valor.append(f"{tabla}.{columna} ({cuantos})")
    if not con_valor:
        return
    raise RuntimeError(
        "Esta migracion no se revierte con datos cargados: "
        + ", ".join(con_valor)
        + ". Bajarla los borra y no hay donde volver a ponerlos; si hace falta "
        "volver, se restaura un respaldo."
    )
