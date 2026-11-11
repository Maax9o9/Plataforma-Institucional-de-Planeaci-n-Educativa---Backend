"""Saber qué restricción violó un `IntegrityError`, y no adivinarlo por el texto."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.shared.infrastructure.db.constraints import viola_la_restriccion


def _error(*, causa: Exception | None) -> IntegrityError:
    """Un `IntegrityError` armado como lo deja asyncpg: la excepción del driver
    cuelga de `orig`, y la que lleva el nombre de la restricción, de su `__cause__`."""
    orig = Exception("duplicate key value violates unique constraint")
    orig.__cause__ = causa
    return IntegrityError("INSERT ...", {}, orig)


def _causa(constraint_name: str) -> Exception:
    causa = Exception("detalle del servidor")
    causa.constraint_name = constraint_name  # type: ignore[attr-defined]
    return causa


def test_reconoce_la_restriccion_por_su_nombre():
    error = _error(causa=_causa("poa_ejercicios_anio_key"))

    assert viola_la_restriccion(error, "poa_ejercicios_anio_key")


def test_otra_restriccion_no_es_la_que_se_pregunta():
    error = _error(causa=_causa("fk_poa_ejercicio_catalogo"))

    assert not viola_la_restriccion(error, "poa_ejercicios_anio_key")


@pytest.mark.parametrize(
    "causa",
    [None, Exception("sin nombre de restricción")],
    ids=["sin_causa", "causa_sin_constraint_name"],
)
def test_un_error_que_no_dice_su_restriccion_no_se_confunde_con_ninguna(causa):
    """Otro driver, u otro tipo de fallo: ante la duda no es la restricción
    preguntada, y quien traduce vuelve a levantar la excepción."""
    assert not viola_la_restriccion(_error(causa=causa), "poa_ejercicios_anio_key")
