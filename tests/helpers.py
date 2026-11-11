"""Ayudantes que comparten las pruebas del POA por ejercicio.

Viven aquí, y no en cada archivo, porque las pruebas de la cédula y de los
nombres arman el mismo escenario -un POA, un ejercicio que cuelga de él- y la
copia de cada una era la siguiente fuente de divergencia. Se importan como
`from helpers import ...`, igual que `from test_ciclo_poa import _account`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.shared.domain.calendar import institutional_today

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

#: El suelo del pozo de años de ejercicio, el mismo del contrato del dominio.
PRIMER_ANIO_DEL_CONTRATO = 2000

#: El techo del pozo de años de ejercicio, que es **del dominio y no del arnés**:
#: `app/modules/periods/domain/entities.py` y cuatro esquemas de tres módulos
#: validan `2000..2200` para rechazar un año escrito con un dedo de más.
#: Ensancharlo para que quepan más pruebas sería resolver por el lado
#: equivocado: lo que se ensancha es el reciclaje, no el techo.
ULTIMO_ANIO_DEL_CONTRATO = 2200

#: Los años que `anio_libre` prestó durante la prueba en curso. `backend_client`
#: lo vacía al empezar cada prueba y, en la variante de PostgreSQL, al terminar
#: devuelve al pozo los que no sostienen nada. Sin esto el pozo se agotaba
#: *dentro* de una sola corrida: medido el 4 de noviembre de 2026, la suite
#: completa dejaba 196 de los 201 años tomados y quedaban cinco libres.
ANIOS_PRESTADOS: set[int] = set()

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
    inicial = next((poa["id"] for poa in listado.json() if poa["nombre"] == "POA 2026"), None)
    if inicial is None:
        nombres = sorted(poa["nombre"] for poa in listado.json())
        pytest.fail(
            "No está el POA sembrado «POA 2026»: `ensure_catalogs()` sólo siembra si la tabla "
            f"de catálogos está vacía, así que alguien creó un POA antes. Hay {nombres}."
        )
    return inicial


#: Lo que hay que leer cuando el pozo se agota. Va en el mensaje y no sólo aquí
#: porque quien lo lea estará mirando la salida de pytest, no este archivo. Y
#: dice la verdad -«se acabaron los años de ejercicio»- en vez de dejar que el
#: fallo aparezca como un reporte roto: medido, agotar el pozo rompe tres
#: pruebas de `test_reportes_poa.py` que nadie tocó.
SE_ACABARON_LOS_ANIOS = "Se acabaron los años de ejercicio"

_QUE_HACER_CUANDO_SE_ACABAN = (
    "El pozo se devuelve al terminar cada prueba -`backend_client`, en "
    "tests/conftest.py, borra los ejercicios que no sostienen nada-, así que lo que "
    "sigue tomado es lo que tiene algo colgando (una cédula) o lo que pide un año "
    f"fijo. Mira eso, no el techo: el {ULTIMO_ANIO_DEL_CONTRATO} es del dominio."
)


def primer_anio_por_venir() -> int:
    """El primer año de ejercicio que todavía no ha empezado.

    Es el suelo por omisión de `anio_libre`, y no el 2000, por una razón medida:
    la estructura de una cédula se cierra al terminar su primer cuatrimestre
    (`_ensure_structure_editable`), así que **una cédula sólo se puede formular
    contra un ejercicio por venir**. Mientras el pozo se gastaba de abajo
    arriba, las pruebas que formulan cédulas recibían años ya pasados al
    principio de la corrida y años futuros al final: funcionaban porque el pozo
    estaba casi lleno, o sea por la posición del archivo en el alfabeto. Al
    devolver los años al pozo, `anio_libre` volvía al 2000 y esas pruebas
    contestaban «No se puede crear una cédula después del primer cuatrimestre».

    Quien necesite de verdad un año ya empezado lo pide con
    `desde=PRIMER_ANIO_DEL_CONTRATO`, y así queda escrito que lo necesita.
    """
    return institutional_today().year + 1


async def anio_libre(client, headers, *, desde: int | None = None) -> int:
    """El primer año, a partir de `desde`, que ningún ejercicio ocupa.

    Sin `desde` empieza en `primer_anio_por_venir()`, que es lo que casi toda
    prueba necesita y lo que hace que el año no dependa de cuántas pruebas
    corrieron antes.

    `poa_ejercicios.anio` es único en todo el sistema y la base de PostgreSQL
    persiste durante la corrida. Se busca desde abajo y no con `max + 1` porque
    otras pruebas piden años fijos (2160 a 2165 en `test_borrado_cedula_poa.py`
    y 2199 en `test_ep08_revision_poa.py`) y subir desde el máximo toparía con
    ellas, o se saldría del 2200 que el contrato admite.

    Lo que entrega queda anotado en `ANIOS_PRESTADOS`: es un préstamo, no un
    gasto. Quien lo devuelve es `backend_client`.
    """
    if desde is None:
        desde = primer_anio_por_venir()
    listado = await client.get(f"{API}/poa/ejercicios", headers=headers)
    assert listado.status_code == 200, listado.text
    ocupados = {ejercicio["anio"] for ejercicio in listado.json()}
    libre = next(
        (anio for anio in range(desde, ULTIMO_ANIO_DEL_CONTRATO + 1) if anio not in ocupados),
        None,
    )
    if libre is None:
        pytest.fail(
            f"{SE_ACABARON_LOS_ANIOS}: no queda ninguno libre entre {desde} y "
            f"{ULTIMO_ANIO_DEL_CONTRATO}, y hay {len(ocupados)} ejercicios en la base. "
            f"{_QUE_HACER_CUANDO_SE_ACABAN}"
        )
    ANIOS_PRESTADOS.add(libre)
    return libre


async def crear_ejercicio_de_un_anio_libre(client, headers, catalogo_id: int) -> dict:
    anio = await anio_libre(client, headers)
    creado = await client.post(
        f"{API}/poa/ejercicios",
        headers=headers,
        json={"anio": anio, "catalogo_id": catalogo_id},
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


def cuatrimestres(anio: int) -> list[dict[str, object]]:
    """Los tres cuatrimestres de un año, como los pide `POST /poa/cedulas`.

    El reparto -enero-abril, mayo-agosto, septiembre-diciembre- es el del
    formato institucional y no es una elección de cada prueba: el esquema exige
    exactamente tres, ordenados y sin traslaparse. Estaba copiado literal en
    ocho sitios.
    """
    return [
        {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
        {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
        {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
    ]


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
