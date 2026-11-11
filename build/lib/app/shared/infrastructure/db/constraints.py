"""Qué restricción de la base violó un `IntegrityError`."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def viola_la_restriccion(exc: IntegrityError, nombre: str) -> bool:
    """¿Esta violación es de la restricción `nombre`, y no de otra?

    Un `except IntegrityError` que traduce *todo* a «ya existe» manda a buscar un
    duplicado cuando lo que falló fue una foránea o un `NOT NULL`: quien lo usa
    pregunta primero por la restricción que sabe traducir y vuelve a levantar la
    excepción si es otra.

    Con asyncpg el nombre de la restricción viaja en la excepción original
    (`orig.__cause__`), no en el texto: preguntarlo ahí evita adivinar por el
    mensaje, que cambia con el idioma del servidor.
    """
    causa = getattr(exc.orig, "__cause__", None)
    return getattr(causa, "constraint_name", None) == nombre
