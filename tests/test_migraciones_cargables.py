"""Ninguna migracion lleva algo que SQLAlchemy tome por parametro.

Es una trampa que no se ve, y que ya salto una vez. `execute_sql_file`
(`app/shared/infrastructure/db/sql_loader.py`) ejecuta cada sentencia con
`op.execute(<cadena>)`, y Alembic la envuelve en `sqlalchemy.text()`. `text()`
busca `:nombre` en **toda** la cadena y no sabe que es un comentario `--`, asi
que un comentario puede dejar la sentencia que le sigue con un parametro sin
valor y matar la migracion.

Lo que salta no es citar una linea: `ver 0022:16` esta a salvo, porque los dos
puntos van pegados a un caracter de palabra y ahi `text()` no mira. Lo que
salta es el mismo numero suelto -entre comillas invertidas, tras un espacio o
tras un parentesis-, que es como lo escribi yo al documentar la 0037: los dos
puntos no siguen a ninguna letra y pasan a ser un parametro. La distincion es
lo bastante fina como para no fiarse de ella a ojo, y de eso se encarga esto.

No se arregla en el cargador a proposito: pasar a `exec_driver_sql` rompe el
modo offline, que `alembic/env.py` implementa con `literal_binds=True`. Asi que
la red se pone aqui, y mira las 37 migraciones de una vez.

Esta prueba nace verde -hoy ninguna trae la trampa- y existe para la 0038.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.shared.infrastructure.db.sql_loader import split_sql

MIGRACIONES = Path(__file__).resolve().parents[1] / "bd" / "migrations"

#: Lo que hay que leer cuando esto falle. Va dentro del mensaje porque quien lo
#: vea va a estar mirando una migracion que no arranca, probablemente con prisa,
#: y el error de SQLAlchemy no apunta al comentario que lo causo.
_POR_QUE = """
Alembic envuelve cada sentencia en `sqlalchemy.text()`, que busca `:nombre` en
toda la cadena sin distinguir el SQL del comentario. Lo de arriba deja la
sentencia con un parametro sin valor, y al migrar sale:

    InvalidRequestError: A value is required for bind parameter '<nombre>'

sin decir donde esta.

Si es un comentario, hay dos salidas. Quitar los dos puntos -«linea 16»- o
pegarlos a la palabra de antes -«0022:16», «0037_poa_por_ejercicio.sql:30»-,
que es la forma que no salta: `text()` no mira unos dos puntos que siguen a una
letra, un digito o un guion bajo. Lo que salta es el numero suelto: `` `:16` ``,
« :16», «(:16)».

Si es SQL y el parametro lo quieres de verdad, esta migracion no es el sitio:
el cargador no le pasa valores a nadie.

Los moldes `::tipo` no cuentan y no hace falta esquivarlos.
"""


def _linea_de(texto: str, nombre: str) -> int:
    """La linea del archivo donde `:nombre` aparece por primera vez."""
    posicion = texto.find(f":{nombre}")
    return texto.count("\n", 0, posicion) + 1 if posicion >= 0 else 0


def test_ninguna_migracion_lleva_un_parametro_sin_valor():
    """Se le pregunta a SQLAlchemy, no a una expresion regular propia.

    Que lo diga el mismo analizador que va a ejecutar la migracion es lo unico
    que no se desalinea con el: una copia de su regla aqui podria aceptar lo
    que alla revienta, que es precisamente el fallo que esto cubre.
    """
    archivos = sorted(MIGRACIONES.glob("*.sql"))
    # Si el glob deja de encontrar nada -un renombre del directorio, una prueba
    # movida de sitio-, lo de abajo pasaria por vacio y la red no estaria
    # puesta sin que nadie lo notara.
    assert archivos, f"no se encontro ninguna migracion en {MIGRACIONES}"

    hallazgos = []
    for ruta in archivos:
        texto = ruta.read_text(encoding="utf-8")
        for sentencia in split_sql(texto):
            for nombre in sorted(text(sentencia).compile().binds):
                hallazgos.append(
                    f"  bd/migrations/{ruta.name}:{_linea_de(texto, nombre)} -> «:{nombre}»"
                )

    assert not hallazgos, (
        "Estas migraciones no se pueden cargar; SQLAlchemy toma por parametro:\n"
        + "\n".join(hallazgos)
        + _POR_QUE
    )
