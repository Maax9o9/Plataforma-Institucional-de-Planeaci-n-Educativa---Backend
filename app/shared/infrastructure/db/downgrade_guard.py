from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

_NOMBRE_SQL_SIN_COMILLAS = re.compile(r"^[a-z_][a-z0-9_]*$")


def _comprobado(nombre: str) -> str:
    if not _NOMBRE_SQL_SIN_COMILLAS.match(nombre):
        raise ValueError(f"«{nombre}» no es un nombre que se pueda interpolar.")
    return nombre


def _negarse(lo_que_se_perderia: list[str]) -> None:
    raise RuntimeError(
        "Esta migracion no se revierte con datos cargados: "
        + ", ".join(lo_que_se_perderia)
        + ". Bajarla los borra y no hay donde volver a ponerlos; si hace falta "
        "volver, se restaura un respaldo."
    )


def rechazar_si_hay_filas(conexion: Connection, *tablas: str) -> None:
    pobladas = []
    for tabla in tablas:
        cuantas = conexion.execute(text(f"SELECT count(*) FROM {_comprobado(tabla)}")).scalar_one()
        if cuantas:
            pobladas.append(f"{tabla} ({cuantas})")
    if pobladas:
        _negarse(pobladas)


def rechazar_si_hay_valores(conexion: Connection, tabla: str, *columnas: str) -> None:
    con_valor = []
    for columna in columnas:
        cuantos = conexion.execute(
            text(f"SELECT count({_comprobado(columna)}) FROM {_comprobado(tabla)}")
        ).scalar_one()
        if cuantos:
            con_valor.append(f"{tabla}.{columna} ({cuantos})")
    if con_valor:
        _negarse(con_valor)
