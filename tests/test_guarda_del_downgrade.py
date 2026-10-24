from __future__ import annotations

import pytest

from app.shared.infrastructure.db.downgrade_guard import (
    rechazar_si_hay_filas,
    rechazar_si_hay_valores,
)

NOMBRES_QUE_NO_SE_INTERPOLAN = [
    "nodos_estrategicos; DROP TABLE instrumentos",
    "public.nodos_estrategicos",
    "Nodos_Estrategicos",
    "nodos-estrategicos",
    "1_tabla",
    "nodos estrategicos",
    "",
]


class _ConexionQueNadieDebeUsar:
    def execute(self, sentencia):
        raise AssertionError(f"la guarda consulto la base con un nombre sin comprobar: {sentencia}")


class _Conteo:
    def __init__(self, cuantas: int) -> None:
        self._cuantas = cuantas

    def scalar_one(self) -> int:
        return self._cuantas


class _ConexionQueApunta:
    def __init__(self, cuantas: int = 0) -> None:
        self.consultas: list[str] = []
        self._cuantas = cuantas

    def execute(self, sentencia):
        self.consultas.append(str(sentencia))
        return _Conteo(self._cuantas)


@pytest.mark.parametrize("nombre", NOMBRES_QUE_NO_SE_INTERPOLAN)
def test_la_guarda_no_interpola_un_nombre_que_no_sea_un_identificador(nombre):
    with pytest.raises(ValueError) as como_tabla:
        rechazar_si_hay_filas(_ConexionQueNadieDebeUsar(), nombre)
    with pytest.raises(ValueError) as como_columna:
        rechazar_si_hay_valores(_ConexionQueNadieDebeUsar(), "instrumento_versiones", nombre)

    assert nombre in str(como_tabla.value)
    assert nombre in str(como_columna.value)


def test_la_guarda_cuenta_filas_de_cada_tabla_y_valores_de_cada_columna():
    por_filas = _ConexionQueApunta()
    por_valores = _ConexionQueApunta()

    rechazar_si_hay_filas(por_filas, "nodos_estrategicos", "instrumento_versiones")
    rechazar_si_hay_valores(por_valores, "nodos_estrategicos", "formula_indicador", "clave")

    assert por_filas.consultas == [
        "SELECT count(*) FROM nodos_estrategicos",
        "SELECT count(*) FROM instrumento_versiones",
    ]
    assert por_valores.consultas == [
        "SELECT count(formula_indicador) FROM nodos_estrategicos",
        "SELECT count(clave) FROM nodos_estrategicos",
    ]


def test_la_guarda_se_niega_nombrando_cada_tabla_y_columna_con_su_conteo():
    with pytest.raises(RuntimeError) as por_filas:
        rechazar_si_hay_filas(_ConexionQueApunta(cuantas=3), "nodos_estrategicos")
    with pytest.raises(RuntimeError) as por_valores:
        rechazar_si_hay_valores(
            _ConexionQueApunta(cuantas=7), "instrumento_versiones", "origen"
        )

    assert "nodos_estrategicos (3)" in str(por_filas.value)
    assert "instrumento_versiones.origen (7)" in str(por_valores.value)
