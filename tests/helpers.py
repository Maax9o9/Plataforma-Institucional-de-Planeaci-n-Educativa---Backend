"""Ayudantes que comparten las pruebas del POA por ejercicio.

Viven aquí, y no en cada archivo, porque las pruebas de la cédula y de los
nombres arman el mismo escenario -un POA, un ejercicio que cuelga de él- y la
copia de cada una era la siguiente fuente de divergencia. Se importan como
`from helpers import ...`, igual que `from test_ciclo_poa import _account`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

API = "/api/v1"

#: Lo que no puede ser el id de un POA, y la validación que lo dice. Las razones
#: están en `IdDePoa`: por arriba y por abajo de lo que cabe en el entero de la
#: base PostgreSQL ni lo acepta como parámetro (y contestaría 500), y el cero no
#: es un id porque los seriales empiezan en 1.
IDS_QUE_NO_PUEDEN_SER_DE_UN_POA = [
    pytest.param(2**31, "less_than_equal", id="mayor_que_el_entero_de_la_base"),
    pytest.param(-(2**31) - 1, "greater_than_equal", id="menor_que_el_entero_de_la_base"),
    pytest.param(0, "greater_than_equal", id="cero"),
]

#: Un id que ningún POA tiene. La base de pruebas es persistente y el id es
#: serial: con uno chico, tarde o temprano habría un POA que lo use. Vive aquí
#: porque lo piden las pruebas del catálogo, las del ejercicio y las de la
#: cédula, y tres copias del mismo número son tres sitios donde dejar de
#: coincidir.
POA_INEXISTENTE = 999999


async def poa_inicial_id(client, headers) -> int:
    """El id del POA que siembra el sistema, para las pruebas que sólo necesitan
    *un* POA del que colgar un ejercicio.

    Se pide por el nombre y por la API, no por el repositorio: así sirve igual
    en cualquier variante, y a quien sólo tiene cliente y cabeceras en la mano.
    """
    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)
    assert listado.status_code == 200, listado.text
    return next(poa["id"] for poa in listado.json() if poa["nombre"] == "POA 2026")


async def anio_libre(client, headers, *, desde: int = 2000) -> int:
    """El primer año, a partir de `desde`, que ningún ejercicio ocupa.

    `poa_ejercicios.anio` es único en todo el sistema y la base de PostgreSQL
    persiste durante la corrida. Se busca desde abajo y no con `max + 1` porque
    otras pruebas piden años fijos (2036, 2160 a 2165, 2197 y 2198) y los
    generadores al azar reparten por todo el rango: subir desde el máximo toparía con ellas, o se
    saldría del 2200 que el contrato admite.

    `desde` es para quien además necesita que el año no haya empezado: la
    estructura de una cédula se cierra al terminar su primer cuatrimestre, así
    que sólo se puede formular en un ejercicio por venir.
    """
    listado = await client.get(f"{API}/poa/ejercicios", headers=headers)
    assert listado.status_code == 200, listado.text
    ocupados = {ejercicio["anio"] for ejercicio in listado.json()}
    return next(anio for anio in range(desde, 2201) if anio not in ocupados)


async def crear_poa(client, headers, anio: int) -> dict:
    """Un POA vacío con nombre único: el nombre es único en todo el sistema."""
    poa = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=headers,
        json={"nombre": f"POA {uuid4().hex[:6]}", "anio": anio, "origen": None},
    )
    assert poa.status_code == 201, poa.text
    return poa.json()


async def crear_ejercicio(client, headers, poa: dict, anio: int) -> dict:
    """Un ejercicio del `anio` que cuelga de `poa` (lo que devolvió `crear_poa`)."""
    creado = await client.post(
        f"{API}/poa/ejercicios",
        headers=headers,
        json={"anio": anio, "catalogo_id": poa["id"]},
    )
    assert creado.status_code == 201, creado.text
    return creado.json()
