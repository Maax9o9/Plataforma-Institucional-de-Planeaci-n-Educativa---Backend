"""El arbol del PIDE en la base: la migracion 0038.

Solo corre contra PostgreSQL: la migracion es SQL crudo y el repositorio en
memoria no la ejecuta. Por eso no usa `backend_client`, que correria tambien la
variante en memoria sin tocar la base: con ella, la mitad de las corridas
pasaria sin ejercer nada.

Cada prueba se siembra a si misma y revierte al salir. No puede apoyarse en lo
que dejo la migracion porque `tests/conftest.py` vacia las tablas de la
aplicacion al arrancar la sesion.

Lo que se vigila aqui es lo que el esquema promete y la aplicacion da por
cierto: el padre explicito, el nivel como dato, la clave sin formato, y que
nada que ya se usa se pueda borrar. Cada violacion se reconoce por el NOMBRE de
la restriccion que la levanto y no solo por el tipo de error: un
`IntegrityError` tambien sale de un NOT NULL o de una foranea de al lado, y una
prueba que lo acepta sin mirar cual puede pasar por el motivo equivocado.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.shared.infrastructure.db.constraints import viola_la_restriccion

#: Los cinco niveles que el capitulo VII del PIDE usa de verdad, de arriba a
#: abajo. Tal como los guarda la columna `tipo`.
NIVELES = (
    "eje",
    "objetivo_general",
    "objetivo_especifico",
    "linea_estrategica",
    "accion",
)


@pytest.fixture
def url() -> str:
    valor = os.getenv("TEST_DATABASE_URL")
    if not valor:
        pytest.skip("TEST_DATABASE_URL no configurada")
    return valor


@pytest.fixture
async def conexion(url):
    """Conexion cuya transaccion se revierte siempre.

    Las pruebas siembran versiones y nodos de verdad; revertir al salir las
    deja repetibles sin ensuciar una base que persiste entre corridas.
    """
    motor = create_async_engine(url)
    try:
        async with motor.connect() as abierta:
            transaccion = await abierta.begin()
            try:
                yield abierta
            finally:
                await transaccion.rollback()
    finally:
        await motor.dispose()


async def _instrumento(conexion: AsyncConnection) -> int:
    """Un instrumento propio: el PIDE sembrado no esta garantizado aqui, y el
    nombre es unico en toda la base."""
    return (
        await conexion.execute(
            text("INSERT INTO instrumentos (nombre) VALUES (:nombre) RETURNING id"),
            {"nombre": f"Instrumento de prueba {uuid4().hex[:8]}"},
        )
    ).scalar_one()


async def _version(conexion: AsyncConnection, instrumento: int, etiqueta: str = "V1") -> int:
    return (
        await conexion.execute(
            text(
                "INSERT INTO instrumento_versiones (instrumento_id, etiqueta, vigente_desde) "
                "VALUES (:instrumento, :etiqueta, '2025-01-01') RETURNING id"
            ),
            {"instrumento": instrumento, "etiqueta": etiqueta},
        )
    ).scalar_one()


async def _nodo(
    conexion: AsyncConnection,
    version: int,
    clave: str,
    tipo: str = "eje",
    padre: int | None = None,
    orden: int = 1,
) -> int:
    return (
        await conexion.execute(
            text(
                "INSERT INTO nodos_estrategicos "
                "(version_id, padre_id, tipo, clave, denominacion, orden) "
                "VALUES (:version, :padre, :tipo, :clave, :denominacion, :orden) RETURNING id"
            ),
            {
                "version": version,
                "padre": padre,
                "tipo": tipo,
                "clave": clave,
                "denominacion": f"Nodo {clave}",
                "orden": orden,
            },
        )
    ).scalar_one()


async def _cadena(conexion: AsyncConnection, version: int, claves: tuple[str, ...]) -> list[int]:
    """Un nodo por nivel, cada uno colgando del anterior. Devuelve los ids de
    arriba a abajo."""
    ids: list[int] = []
    for tipo, clave in zip(NIVELES, claves, strict=True):
        ids.append(await _nodo(conexion, version, clave, tipo, ids[-1] if ids else None))
    return ids


def _columna_sin_valor(error: IntegrityError) -> str | None:
    """La columna NOT NULL que la sentencia dejo sin valor.

    Una NOT NULL no tiene nombre de restriccion, asi que `viola_la_restriccion`
    no sirve: lo que trae el error es el nombre de la columna, y viaja en la
    excepcion del driver igual que el de una restriccion. Preguntarlo ahi evita
    adivinar por el texto, que cambia con el idioma del servidor.
    """
    causa = getattr(error.orig, "__cause__", None)
    return getattr(causa, "column_name", None)


async def _intentar(conexion: AsyncConnection, sql: str, parametros: dict) -> IntegrityError:
    """Ejecuta algo que tiene que reventar y devuelve el error.

    Va en un SAVEPOINT: en PostgreSQL una sentencia fallida deja abortada la
    transaccion entera, y la prueba sigue sembrando despues de la falla.
    """
    with pytest.raises(IntegrityError) as caido:
        async with conexion.begin_nested():
            await conexion.execute(text(sql), parametros)
    return caido.value


@pytest.mark.asyncio
async def test_el_esquema_del_arbol_existe_con_padre_y_nivel_como_datos(conexion):
    """El contrato que las tareas siguientes dan por cierto: las columnas, y
    cuales admiten NULL. `padre_id` es la unica que debe admitirlo -el eje no
    tiene padre-; si otra lo admitiera, un nodo podria quedar sin version o sin
    nivel."""
    filas = (
        await conexion.execute(
            text(
                "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('nodos_estrategicos', 'instrumento_versiones')"
            )
        )
    ).all()
    nulables = {(tabla, columna): es for tabla, columna, es in filas}

    assert {
        columna: nulables.get(("nodos_estrategicos", columna))
        for columna in (
            "id",
            "version_id",
            "padre_id",
            "tipo",
            "clave",
            "denominacion",
            "orden",
            "activo",
        )
    } == {
        "id": "NO",
        "version_id": "NO",
        "padre_id": "YES",
        "tipo": "NO",
        "clave": "NO",
        "denominacion": "NO",
        "orden": "NO",
        "activo": "NO",
    }

    # `publicada_en` admite NULL a proposito: una version cargada y todavia no
    # publicada es una version en borrador.
    assert {
        columna: nulables.get(("instrumento_versiones", columna))
        for columna in ("id", "instrumento_id", "etiqueta", "vigente_desde", "publicada_en")
    } == {
        "id": "NO",
        "instrumento_id": "NO",
        "etiqueta": "NO",
        "vigente_desde": "NO",
        "publicada_en": "YES",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "clave", ["E1.L2.A3", "1.1.1.1.1", "12.10.11.13.14", "1.a", "A", "1.ñ", "Á2.3"]
)
async def test_la_clave_no_exige_formato_numerico(conexion, clave):
    """«E1.L2.A3» es una clave valida: la fija el documento fuente, y el orden
    sale del arbol, no de ella. Cada valor mata una regla distinta que alguien
    podria querer poner: solo digitos, digitos con puntos, mayusculas, una
    longitud corta, y un CHECK que exigiera ASCII -que los dos valores con
    acento delatan, y que ningun otro valor de prueba veria-."""
    version = await _version(conexion, await _instrumento(conexion))
    # El padre no contiene la clave del hijo: quien derive la jerarquia de la
    # clave se equivocaria aqui.
    eje = await _nodo(conexion, version, "9")
    nodo = await _nodo(conexion, version, clave, "objetivo_general", padre=eje)

    guardada = (
        await conexion.execute(
            text("SELECT clave FROM nodos_estrategicos WHERE id = :id"), {"id": nodo}
        )
    ).scalar_one()
    assert guardada == clave


@pytest.mark.asyncio
async def test_un_nodo_nuevo_nace_activo_y_guarda_el_texto_completo(conexion):
    """Dos cosas que la carga del PIDE da por hechas: que lo que se carga se
    puede elegir sin decirlo -un nodo que naciera inactivo desapareceria de
    todos los selectores-, y que la denominacion cabe entera. Las acciones del
    capitulo VII son parrafos, no etiquetas."""
    version = await _version(conexion, await _instrumento(conexion))
    largo = "Fortalecer el Programa Institucional de Tutorias. " * 40

    nodo = (
        await conexion.execute(
            text(
                "INSERT INTO nodos_estrategicos "
                "(version_id, padre_id, tipo, clave, denominacion, orden) "
                "VALUES (:version, NULL, 'eje', '1', :denominacion, 3) "
                "RETURNING activo, denominacion, orden"
            ),
            {"version": version, "denominacion": largo},
        )
    ).one()
    assert nodo.activo is True
    assert nodo.denominacion == largo
    assert nodo.orden == 3


@pytest.mark.asyncio
async def test_dos_nodos_hermanos_no_repiten_clave(conexion):
    """Hermanos son los que comparten padre. Los dos duplicados difieren en
    todo lo demas -nivel, texto y orden-, para que la unica razon por la que
    choquen sea la clave: una unica que incluyera alguna de esas columnas los
    dejaria pasar."""
    version = await _version(conexion, await _instrumento(conexion))
    eje = await _nodo(conexion, version, "1")
    await _nodo(conexion, version, "1.1", "objetivo_general", padre=eje, orden=1)

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos "
        "(version_id, padre_id, tipo, clave, denominacion, orden) "
        "VALUES (:version, :padre, 'accion', '1.1', 'Otro texto', 7)",
        {"version": version, "padre": eje},
    )
    assert viola_la_restriccion(error, "uq_nodo_estrategico_hermano_clave")


@pytest.mark.asyncio
async def test_dos_ejes_de_la_misma_version_no_repiten_clave(conexion):
    """Los ejes no tienen padre, y en una UNIQUE comun dos NULL no se
    consideran iguales: `UNIQUE (version_id, padre_id, clave)` a secas deja
    cargar el eje «1» dos veces en la misma version. Es el caso que la
    restriccion existe para cubrir y el unico que ella sola no cubriria."""
    version = await _version(conexion, await _instrumento(conexion))
    await _nodo(conexion, version, "1")

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos "
        "(version_id, padre_id, tipo, clave, denominacion, orden) "
        "VALUES (:version, NULL, 'eje', '1', 'Otro eje', 2)",
        {"version": version},
    )
    assert viola_la_restriccion(error, "uq_nodo_estrategico_hermano_clave")


@pytest.mark.asyncio
async def test_la_misma_clave_cabe_bajo_otro_padre_y_en_otra_version(conexion):
    """La contraparte: la unicidad es entre hermanos de una version, no mas
    ancha. Una que valiera para toda la version, o para toda la base, impediria
    cargar la version siguiente del PIDE -que repite casi todas las claves- y
    obligaria a que la clave dijera donde cuelga, que es justo lo que se evita."""
    instrumento = await _instrumento(conexion)
    primera = await _version(conexion, instrumento, "V1")
    segunda = await _version(conexion, instrumento, "V2")

    # Mismo eje «1» en las dos versiones.
    eje_uno = await _nodo(conexion, primera, "1")
    await _nodo(conexion, segunda, "1")
    # Y la misma clave «1.1» colgando de dos ejes distintos de una misma version.
    eje_dos = await _nodo(conexion, primera, "2")
    await _nodo(conexion, primera, "1.1", "objetivo_general", padre=eje_uno)
    await _nodo(conexion, primera, "1.1", "objetivo_general", padre=eje_dos)

    cuantas = (
        await conexion.execute(
            text(
                "SELECT count(*) FROM nodos_estrategicos "
                "WHERE clave IN ('1', '1.1') AND version_id IN (:primera, :segunda)"
            ),
            {"primera": primera, "segunda": segunda},
        )
    ).scalar_one()
    assert cuantas == 4


@pytest.mark.asyncio
async def test_un_nodo_no_cuelga_de_un_padre_de_otra_version(conexion):
    """Una foranea de una sola columna -`padre_id`- deja que la accion de la
    version 2 cuelgue de una linea de la version 1: el arbol de cada version
    dejaria de ser suyo y publicar una arrastraria nodos de la otra."""
    instrumento = await _instrumento(conexion)
    primera = await _version(conexion, instrumento, "V1")
    segunda = await _version(conexion, instrumento, "V2")
    eje = await _nodo(conexion, primera, "1")

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos "
        "(version_id, padre_id, tipo, clave, denominacion, orden) "
        "VALUES (:version, :padre, 'objetivo_general', '1.1', 'Colgado de otra version', 1)",
        {"version": segunda, "padre": eje},
    )
    assert viola_la_restriccion(error, "fk_nodo_estrategico_padre")

    # El mismo hijo en la version del padre si entra: lo que fallo arriba fue
    # la version, no otra cosa de la fila.
    await _nodo(conexion, primera, "1.1", "objetivo_general", padre=eje)


@pytest.mark.asyncio
async def test_los_cinco_niveles_cuelgan_en_cadena_y_el_ancestro_se_consulta(conexion):
    """La clave de cada nodo no dice nada de sus ancestros -«Q», «R»...-, y aun
    asi la accion se rastrea hasta su eje: el ancestro se consulta por el padre,
    nunca se deriva partiendo la clave."""
    version = await _version(conexion, await _instrumento(conexion))
    ids = await _cadena(conexion, version, ("Q", "R", "S", "T", "U"))

    ancestros = (
        await conexion.execute(
            text(
                "WITH RECURSIVE ascenso AS ("
                "  SELECT id, padre_id, tipo, 0 AS distancia "
                "  FROM nodos_estrategicos WHERE id = :accion "
                "  UNION ALL "
                "  SELECT n.id, n.padre_id, n.tipo, a.distancia + 1 "
                "  FROM nodos_estrategicos n JOIN ascenso a ON n.id = a.padre_id"
                ") SELECT tipo FROM ascenso WHERE distancia > 0 ORDER BY distancia"
            ),
            {"accion": ids[-1]},
        )
    ).scalars()
    assert list(ancestros) == list(reversed(NIVELES[:-1]))


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo", NIVELES)
async def test_cada_uno_de_los_cinco_niveles_es_un_tipo_valido(conexion, tipo):
    """Uno por uno, no en bloque: un CHECK al que le falta un nivel dejaria
    pasar a los otros cuatro y la prueba en bloque lo veria igual de verde si
    el que falta no fuera el que se mira."""
    version = await _version(conexion, await _instrumento(conexion))
    await _nodo(conexion, version, "1", tipo)


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo", ["", "Eje", "EJE", "meta", "objetivo", "linea", "ACCION"])
async def test_un_nivel_que_el_pide_no_usa_no_entra(conexion, tipo):
    """El CHECK es cerrado: se amplia con una migracion si aparece otro nivel,
    no se acepta cualquier texto. Las mayusculas cuentan porque el codigo
    compara el valor tal cual."""
    version = await _version(conexion, await _instrumento(conexion))

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos "
        "(version_id, padre_id, tipo, clave, denominacion, orden) "
        "VALUES (:version, NULL, :tipo, '1', 'Nivel ajeno', 1)",
        {"version": version, "tipo": tipo},
    )
    assert viola_la_restriccion(error, "chk_nodo_estrategico_tipo")


@pytest.mark.asyncio
async def test_una_version_no_repite_etiqueta_dentro_de_su_instrumento(conexion):
    """La etiqueta es lo que distingue una version de otra ante quien la elige:
    dos con la misma serian indistinguibles. Y es lo que permite cargar el PIDE
    mas de una vez sin duplicar su cabecera. Otro instrumento si puede llamarse
    igual a su version."""
    instrumento = await _instrumento(conexion)
    await _version(conexion, instrumento, "PIDE 2025-2030")

    error = await _intentar(
        conexion,
        "INSERT INTO instrumento_versiones (instrumento_id, etiqueta, vigente_desde) "
        "VALUES (:instrumento, 'PIDE 2025-2030', '2031-01-01')",
        {"instrumento": instrumento},
    )
    assert viola_la_restriccion(error, "uq_instrumento_version_etiqueta")

    await _version(conexion, await _instrumento(conexion), "PIDE 2025-2030")


@pytest.mark.asyncio
async def test_una_version_nace_en_borrador_y_su_vigencia_la_decide_quien_carga(conexion):
    """«NULL mientras la version esta en borrador» lo dice el comentario de la
    columna y no lo fijaba ninguna prueba: con `publicada_en DEFAULT now()`
    toda version cargada nace publicada y nadie se entera. Es el analogo de
    `activo`, que si tiene su prueba.

    Y `vigente_desde` no tiene valor por omision. Desde cuando rige una version
    lo dice el documento, no el dia en que alguien la cargo: con un
    `DEFAULT CURRENT_DATE` la fila sin vigencia entra y se queda con una fecha
    inventada. Por eso se inserta sin ella y se exige que la base la reclame.
    """
    instrumento = await _instrumento(conexion)

    fila = (
        await conexion.execute(
            text(
                "INSERT INTO instrumento_versiones (instrumento_id, etiqueta, vigente_desde) "
                "VALUES (:instrumento, 'PIDE 2025-2030', '2025-09-01') "
                "RETURNING publicada_en, vigente_desde"
            ),
            {"instrumento": instrumento},
        )
    ).one()
    assert fila.publicada_en is None
    assert fila.vigente_desde == date(2025, 9, 1)

    error = await _intentar(
        conexion,
        "INSERT INTO instrumento_versiones (instrumento_id, etiqueta) "
        "VALUES (:instrumento, 'Sin vigencia')",
        {"instrumento": instrumento},
    )
    assert _columna_sin_valor(error) == "vigente_desde"


@pytest.mark.asyncio
async def test_el_orden_se_exige_y_no_es_unico_entre_hermanos(conexion):
    """`orden` es la invariante central de esta migracion -la clave no ordena- y
    sus dos mitades se sostenian de rebote.

    Con `orden NOT NULL DEFAULT 0`, quien carga sin decir el orden deja a todos
    los hermanos empatados en cero y el listado los desempata por id sin que
    nadie lo haya decidido: la columna lo exige para que el orden sea un dato
    del documento y no un accidente de la carga.

    Y `orden` no es unico entre hermanos: dos nodos con el mismo orden entran, y
    el desempate por id es parte del contrato del listado. Una
    `UNIQUE (version_id, padre_id, orden)` lo impediria, y hoy solo muere porque
    el ayudante de este archivo usa `orden=1` por omision: cambiar ese valor por
    omision la deja viva. Los dos hermanos empatados difieren en nivel, clave y
    texto, asi que lo unico que comparten es el orden.
    """
    version = await _version(conexion, await _instrumento(conexion))
    eje = await _nodo(conexion, version, "1")

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos (version_id, padre_id, tipo, clave, denominacion) "
        "VALUES (:version, :padre, 'objetivo_general', '1.1', 'Sin orden')",
        {"version": version, "padre": eje},
    )
    assert _columna_sin_valor(error) == "orden"

    await _nodo(conexion, version, "1.2", "objetivo_general", padre=eje, orden=4)
    await _nodo(conexion, version, "1.3", "linea_estrategica", padre=eje, orden=4)

    empatados = (
        await conexion.execute(
            text(
                "SELECT count(*) FROM nodos_estrategicos "
                "WHERE padre_id = :padre AND orden = 4"
            ),
            {"padre": eje},
        )
    ).scalar_one()
    assert empatados == 2


@pytest.mark.asyncio
async def test_un_nodo_retirado_sigue_ocupando_su_clave(conexion):
    """«No se borra, se desactiva» implica que el «1.1» retirado sigue
    reservando «1.1» entre sus hermanos. La unicidad escrita como indice
    parcial `WHERE activo` -con el mismo nombre, asi que nada se nota- pasaba
    todas las pruebas, y con ella cargar otra vez el PIDE crearia un segundo
    «1.1» al lado del retirado: la carga dejaria de ser idempotente y reactivar
    el retirado chocaria con el nuevo. De esto dependen la carga y el 409 al
    crear.
    """
    version = await _version(conexion, await _instrumento(conexion))
    eje = await _nodo(conexion, version, "1")
    retirado = await _nodo(conexion, version, "1.1", "objetivo_general", padre=eje)
    await conexion.execute(
        text("UPDATE nodos_estrategicos SET activo = FALSE WHERE id = :id"),
        {"id": retirado},
    )

    error = await _intentar(
        conexion,
        "INSERT INTO nodos_estrategicos "
        "(version_id, padre_id, tipo, clave, denominacion, orden) "
        "VALUES (:version, :padre, 'accion', '1.1', 'Con la clave del retirado', 2)",
        {"version": version, "padre": eje},
    )
    assert viola_la_restriccion(error, "uq_nodo_estrategico_hermano_clave")


@pytest.mark.asyncio
async def test_el_nivel_es_un_dato_y_el_esquema_no_lo_ata_a_la_posicion(conexion):
    """Lo que el esquema promete del nivel es el CHECK de los cinco valores. Lo
    que **no** promete es donde puede colgar cada uno: no hay
    `CHECK ((tipo = 'eje') = (padre_id IS NULL))` ni nada que haga del eje la
    unica raiz, y las dos cosas se fijaban por accidente -porque otra prueba
    inserta los cinco niveles con `padre_id` nulo-. Colgarlos de un eje, que es
    la refactorizacion natural de esa prueba, dejaba vivas a las dos reglas.

    Tres filas lo dicen a proposito: dos ejes raiz de la misma version -el
    capitulo VII tiene varios-, una raiz que no es un eje, y una accion
    colgando directo de un eje, que es el salto de niveles que el documento
    trae.

    La cadena «el hijo va mas abajo que el padre» no vive aqui sino en el
    dominio (`strategic_tree_entities`), y por eso esta prueba no la contradice:
    la base guarda el nivel, no lo ordena.
    """
    version = await _version(conexion, await _instrumento(conexion))
    primer_eje = await _nodo(conexion, version, "1")
    await _nodo(conexion, version, "2", orden=2)
    await _nodo(conexion, version, "3", "objetivo_general", orden=3)
    await _nodo(conexion, version, "1.1", "accion", padre=primer_eje)

    filas = (
        await conexion.execute(
            text(
                "SELECT tipo, padre_id FROM nodos_estrategicos "
                "WHERE version_id = :version ORDER BY id"
            ),
            {"version": version},
        )
    ).all()
    assert [(tipo, padre is None) for tipo, padre in filas] == [
        ("eje", True),
        ("eje", True),
        ("objetivo_general", True),
        ("accion", False),
    ]


async def _indicador(conexion: AsyncConnection, nodo: int | None) -> int:
    """Un indicador del catalogo nacional, con su area y su responsable."""
    sufijo = uuid4().hex[:8]
    area = (
        await conexion.execute(
            text("INSERT INTO areas (nombre) VALUES (:nombre) RETURNING id"),
            {"nombre": f"Area de prueba {sufijo}"},
        )
    ).scalar_one()
    usuario = (
        await conexion.execute(
            text(
                "INSERT INTO usuarios (nombre, correo, hash_password) "
                "VALUES ('Prueba 0038', :correo, 'test-only-hash') RETURNING id"
            ),
            {"correo": f"migracion-0038-{sufijo}@example.com"},
        )
    ).scalar_one()
    return (
        await conexion.execute(
            text(
                "INSERT INTO indicadores (clave, nombre, metodo_calculo, unidad_medida, "
                "area_id, responsable_id, periodicidad, nodo_id) "
                "VALUES (:clave, 'Indicador de prueba', '(a / b) * 100', 'Porcentaje', "
                ":area, :usuario, 'anual', :nodo) RETURNING id"
            ),
            {"clave": f"IND-{sufijo}", "area": area, "usuario": usuario, "nodo": nodo},
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_un_indicador_puede_o_no_apuntar_a_un_nodo(conexion):
    """`nodo_id` es opcional: los indicadores que ya existen no cuelgan de
    ningun nodo y siguen siendo validos, y los que si cuelgan guardan a cual.

    El nodo que se usa se elige a proposito entre varios y se comprueba que su
    id **no** existe en `instrumento_versiones`. Corrida sola tras el
    `RESTART IDENTITY` de la sesion, la version y el primer nodo valen los dos
    1, asi que una foranea apuntando a la tabla equivocada entra igual y la
    prueba pasa por coincidencia: en la corrida completa muere por deriva de
    las secuencias, que es un dato que nadie decidio.
    """
    version = await _version(conexion, await _instrumento(conexion))
    nodos = [await _nodo(conexion, version, str(numero), orden=numero) for numero in (1, 2, 3)]
    nodo = next(identificador for identificador in nodos if identificador != version)
    es_tambien_una_version = (
        await conexion.execute(
            text("SELECT count(*) FROM instrumento_versiones WHERE id = :id"),
            {"id": nodo},
        )
    ).scalar_one()
    assert es_tambien_una_version == 0

    sin_nodo = await _indicador(conexion, None)
    con_nodo = await _indicador(conexion, nodo)

    guardados = dict(
        (
            await conexion.execute(
                text("SELECT id, nodo_id FROM indicadores WHERE id IN (:uno, :otro)"),
                {"uno": sin_nodo, "otro": con_nodo},
            )
        ).all()
    )
    assert guardados == {sin_nodo: None, con_nodo: nodo}

    # Y no puede apuntar a un nodo que no existe.
    error = await _intentar(
        conexion,
        "UPDATE indicadores SET nodo_id = -1 WHERE id = :id",
        {"id": sin_nodo},
    )
    assert viola_la_restriccion(error, "fk_indicador_nodo")


@pytest.mark.asyncio
async def test_lo_que_ya_se_usa_no_se_borra(conexion):
    """No hay borrado: se desactiva. Cada foranea del arbol es RESTRICT, y se
    prueba por la que cuelga de cada cosa que se podria querer borrar. Una
    CASCADE se llevaria el arbol entero con su version, y una SET NULL
    convertiria en eje a un nodo cuyo padre se borro."""
    instrumento = await _instrumento(conexion)
    version = await _version(conexion, instrumento)
    eje = await _nodo(conexion, version, "1")
    objetivo = await _nodo(conexion, version, "1.1", "objetivo_general", padre=eje)
    await _indicador(conexion, objetivo)

    # Un nodo con hijos.
    padre = await _intentar(conexion, "DELETE FROM nodos_estrategicos WHERE id = :id", {"id": eje})
    assert viola_la_restriccion(padre, "fk_nodo_estrategico_padre")

    # Un nodo del que cuelga un indicador (no tiene hijos, asi que la unica
    # razon por la que no se borra es el indicador).
    indicado = await _intentar(
        conexion, "DELETE FROM nodos_estrategicos WHERE id = :id", {"id": objetivo}
    )
    assert viola_la_restriccion(indicado, "fk_indicador_nodo")

    # Una version con nodos.
    publicada = await _intentar(
        conexion, "DELETE FROM instrumento_versiones WHERE id = :id", {"id": version}
    )
    assert viola_la_restriccion(publicada, "fk_nodo_estrategico_version")

    # Un instrumento con versiones.
    versionado = await _intentar(
        conexion, "DELETE FROM instrumentos WHERE id = :id", {"id": instrumento}
    )
    assert viola_la_restriccion(versionado, "fk_instrumento_version_instrumento")


@pytest.mark.asyncio
async def test_todas_las_foraneas_del_arbol_son_restrict(conexion):
    """Lo de arriba prueba el comportamiento; esto prueba la declaracion, que
    es lo que no se ve desde fuera: `NO ACTION` -el valor por omision de
    PostgreSQL- se porta igual que RESTRICT en cualquier sentencia suelta y solo
    difiere cuando la restriccion es diferible. Que el proyecto no borre se
    escribe con RESTRICT, y esto es lo que lo distingue de no haberlo escrito.

    Mira las foraneas de las dos tablas nuevas y la que `indicadores` les
    agrega. No mira todas las que apuntan al arbol: las de las tareas que vienen
    -las actividades de un area- son suyas y se vigilaran donde nazcan.
    """
    filas = (
        await conexion.execute(
            text(
                "SELECT c.conname, c.confdeltype::text FROM pg_constraint c "
                "WHERE c.contype = 'f' AND ("
                "  c.conrelid IN ("
                "    'nodos_estrategicos'::regclass, 'instrumento_versiones'::regclass) "
                "  OR (c.conrelid = 'indicadores'::regclass "
                "      AND c.confrelid = 'nodos_estrategicos'::regclass))"
            )
        )
    ).all()

    assert {conname for conname, _ in filas} == {
        "fk_nodo_estrategico_version",
        "fk_nodo_estrategico_padre",
        "fk_instrumento_version_instrumento",
        "fk_indicador_nodo",
    }
    assert [conname for conname, tipo in filas if tipo != "r"] == []
