"""La suite no puede escribir en la base de desarrollo, y algo tiene que decirlo.

Es una red, no un cambio de diseño. `Settings` sigue leyendo el `.env` como
siempre —si eso debe cambiar es decisión de producto—; lo que aquí se sujeta es
que las pruebas **digan a qué base van**.

La trampa, medida y no supuesta: `app/core/config.py` declara `env_file=".env"`,
así que

    Settings(environment="testing", secret_key="...")   # sin database_url

devuelve `database_url = …@localhost:5433/planeacion`, **la base de desarrollo**.
Y `create_app` arma los adaptadores de SQLAlchemy en cuanto hay URL. O sea que
omitir un argumento —no equivocarse en él: omitirlo— pone la suite entera a
escribir en la base de la que vive la pantalla.

No es hipotético. Le pasó al revisor de esta misma rama: construyó
`create_app(Settings(...))` sin `database_url` dando por hecho que sin él iría a
una base de pruebas, y dejó filas en `planeacion`, una de las cuales rompió la
pestaña de indicadores del POA 2026. Las 522 pruebas de entonces pasaron sin
notar nada, porque **ninguna miraba a qué base estaban conectadas**.

Las tres pruebas de abajo son las tres caras de lo mismo: la primera mira el
**código** —que el argumento esté escrito, incluso en un fixture que todavía no
existe—, la segunda mira el **resultado** —a qué base apuntan de verdad las
aplicaciones que la suite construye— y la tercera mira la que existe **por el
solo hecho de importar**, que es la que nadie buscaba. Las dos primeras mueren
si alguien le quita el `database_url=None` explícito al fixture `app` de
`tests/conftest.py`.

**El agujero de esta red, dicho aquí para que nadie la crea cerrada:** no caza
una prueba que **sí** diga a qué base va y nombre una real. La primera mira que
el argumento esté escrito, y ahí lo está; la segunda sólo mira los dos fixtures,
y una prueba puede construir su propia aplicación. Pasó **dos veces**, las dos
arregladas a mano y ninguna por esta red: `tests/test_db_wiring.py` tenía la URL
de desarrollo escrita a mano -medido: volver a ponerla deja la suite entera en
verde-, y `tests/test_cors.py` nombraba `planeacion` en el **5432**, donde en la
máquina de desarrollo hay un PostgreSQL escuchando de verdad. Las dos llevan
ahora una URL imposible. Si mañana vuelve a aparecer una base real en `tests/`,
esto no lo va a decir.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

_TESTS = Path(__file__).resolve().parent

#: Lo que hay que mirar cuando una de estas dos pruebas muere. Va en el mensaje
#: y no sólo en este archivo, porque el que la lea a las tres de la mañana está
#: leyendo la salida de pytest, no el código de la prueba.
_QUE_HACER = (
    "`Settings(...)` sin `database_url` NO cae en una base de pruebas: "
    "`app/core/config.py` declara `env_file=\".env\"` y el `.env` apunta a la "
    "base de desarrollo. Pásale `database_url` explícito (el `None` del fixture "
    "`app` de tests/conftest.py, o `TEST_DATABASE_URL`)."
)


def _es_settings(nodo: ast.AST) -> bool:
    return (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Name)
        and nodo.func.id == "Settings"
    )


def _ambitos_que_construyen_settings(ruta: Path) -> list[tuple[str, str]]:
    """Las funciones de `ruta` que construyen un `Settings`, con su código.

    Se mira la función entera y no sólo los argumentos de la llamada porque hay
    un sitio que construye con `Settings(**base)`
    (`test_ajustes_api_03.py`): el argumento está, pero en el diccionario de
    arriba. Buscar el nombre en el cuerpo de la función acierta en los dos
    casos.

    Lo que este barrido **no** ve, y por eso existe la prueba de al lado: un
    diccionario armado en otro módulo, o `Settings` importado con otro nombre.
    """
    codigo = ruta.read_text(encoding="utf-8")
    arbol = ast.parse(codigo)
    encontrados = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if any(_es_settings(hijo) for hijo in ast.walk(nodo)):
            encontrados.append((nodo.name, ast.get_source_segment(codigo, nodo) or ""))
    return encontrados


def test_ninguna_prueba_construye_settings_sin_decir_a_que_base_va():
    """El lado del código: el argumento tiene que estar escrito.

    Cubre también los fixtures que todavía no existen, que es lo que la prueba
    de al lado no puede hacer: el barrido es sobre `tests/*.py`, no sobre los
    dos fixtures de hoy.

    Sólo sobre `tests/`: que el código de producción lea el `.env` cuando no se
    le dice nada **es lo correcto**, y es justo lo que hace al desplegar.
    """
    sin_decirlo = []
    ambitos = []
    for ruta in sorted(_TESTS.glob("*.py")):
        for nombre, codigo in _ambitos_que_construyen_settings(ruta):
            ambitos.append(f"{ruta.name}::{nombre}")
            if "database_url" not in codigo:
                sin_decirlo.append(f"{ruta.name}::{nombre}")

    # Que el barrido de verdad esté mirando algo. Sin esto, renombrar el import
    # de `Settings` dejaría esta prueba pasando por no encontrar nada, que es la
    # forma más silenciosa de perder una red. Los dos fixtures de `conftest.py`
    # se nombran uno por uno porque son los que gobiernan toda la suite.
    assert "conftest.py::app" in ambitos, ambitos
    assert "conftest.py::backend_client" in ambitos, ambitos
    assert len(ambitos) >= 8, ambitos

    assert sin_decirlo == [], (
        f"Construyen `Settings` sin `database_url`: {sin_decirlo}. {_QUE_HACER}"
    )


def _url_visible(url) -> str:
    """La URL en texto y sin la contraseña: esto sale en la salida de pytest y
    en el registro de CI."""
    return make_url(str(url)).render_as_string(hide_password=True)


@pytest.mark.asyncio
async def test_las_aplicaciones_de_la_suite_no_apuntan_a_la_base_de_desarrollo(
    app, backend_client
):
    """El lado del resultado: a qué base están conectadas de verdad.

    Los dos fixtures que usan casi todas las pruebas, cada uno con su
    invariante:

    - `app` es el de memoria. Su `database_url=None` es **explícito**, así que
      no debe haber motor ninguno. Si aparece uno, el `None` se cayó y el motor
      es el del `.env`.
    - `backend_client` corre en sus dos variantes. En memoria, sin motor; en
      PostgreSQL, el motor tiene que ser **exactamente** `TEST_DATABASE_URL` y
      no cualquier otra base que conteste.

    La contraseña no se compara: `render_as_string(hide_password=True)` la tapa
    en los dos lados, y lo que importa es el servidor, el puerto y el nombre de
    la base.
    """
    aplicacion, _ = backend_client

    assert app.state.db_engine is None, (
        "El fixture `app` tiene motor de base de datos, y no debería: apunta a "
        f"{_url_visible(app.state.db_engine.url)}. {_QUE_HACER}"
    )

    motor = aplicacion.state.db_engine
    if motor is None:
        return
    esperada = os.environ["TEST_DATABASE_URL"]
    assert _url_visible(motor.url) == _url_visible(esperada), (
        f"El fixture `backend_client` apunta a {_url_visible(motor.url)} y "
        f"TEST_DATABASE_URL es {_url_visible(esperada)}. {_QUE_HACER}"
    )


def test_la_aplicacion_de_modulo_no_abre_conexion_contra_su_base():
    """La tercera cara: la aplicación que existe **por el solo hecho de
    importar**, y que nadie estaba mirando.

    `app/core/app_factory.py` termina con `app = create_app()` —sin argumentos,
    o sea el `.env`—, `app/main.py` la reexporta y `tests/conftest.py` importa
    de `app.main`. Así que en **cada** corrida de la suite existe una aplicación
    apuntando a la base de desarrollo, con sus adaptadores de SQLAlchemy ya
    armados. Hoy no abre un solo socket —nadie la usa; es la que sirve uvicorn
    en producción—, y eso es justo lo que esto sujeta: está a una línea de ser
    real.

    Que `create_app()` sin argumentos lea el `.env` **es lo correcto**: es lo
    que hace al desplegar. Lo que no puede volver a pasar desapercibido es que
    la suite empiece a conectarse por ahí.

    Se miran los **dos** contadores del pool y no sólo `checkedout()`: una
    conexión que se abrió y se devolvió deja `checkedout() == 0` y
    `checkedin() == 1`, así que `checkedout()` por su cuenta no vería la que ya
    terminó. Los dos en cero significan «nunca se conectó», que es la
    afirmación que hace falta.
    """
    from app.main import app as aplicacion_de_modulo

    motor = aplicacion_de_modulo.state.db_engine
    if motor is None:
        pytest.skip("Sin `.env` no hay motor de módulo que vigilar (es el caso de CI).")

    pool = motor.sync_engine.pool
    assert (pool.checkedin(), pool.checkedout()) == (0, 0), (
        "La aplicación de módulo abrió conexiones contra "
        f"{_url_visible(motor.url)}: checkedin={pool.checkedin()}, "
        f"checkedout={pool.checkedout()}. Esa aplicación sale de `create_app()` "
        "sin argumentos (`app/core/app_factory.py`), o sea del `.env`, y existe "
        "sólo porque `tests/conftest.py` importa de `app.main`. Si la suite se "
        "conecta por ahí, está escribiendo en la base de desarrollo."
    )
