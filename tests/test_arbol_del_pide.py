"""El árbol del PIDE desde la aplicación: entidades y los dos repositorios.

Cada prueba corre contra el repositorio en memoria **y** contra el de
PostgreSQL. La variante de PostgreSQL no usa `backend_client` -que corre también
la memoria sin tocar la base-: monta el repositorio sobre una conexión propia
cuya transacción se revierte al salir, así que cada prueba siembra lo suyo y no
deja nada. Salta si falta `TEST_DATABASE_URL`; la variante en memoria corre
siempre.

La memoria no tiene esquema, y lo que en PostgreSQL imponen el `CHECK` del nivel
o la `UNIQUE` entre hermanos tiene que cumplirse igual en ella. Por eso casi
todo se prueba por las dos: una regla que sólo la base hace cumplir pasaría en
una variante y no en la otra.

Cada prueba dice, en su docstring, **qué regla equivocada acertaría con datos
descuidados** y qué datos la delatan. Un dato que no distingue la regla correcta
de la equivocada no mide nada.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date
from itertools import count
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
)
from app.modules.institutional_catalogs.infrastructure.models import (
    InstrumentModel,
    InstrumentVersionModel,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_repository import (
    InMemoryStrategicTreeRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)
from app.shared.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ResourceNotFoundError,
    ValidationError,
)

EJE = NodeKind.EJE
OBJETIVO_GENERAL = NodeKind.OBJETIVO_GENERAL
OBJETIVO_ESPECIFICO = NodeKind.OBJETIVO_ESPECIFICO
LINEA = NodeKind.LINEA_ESTRATEGICA
ACCION = NodeKind.ACCION

#: De arriba a abajo, tal como el capítulo VII del PIDE los encadena.
NIVELES = (EJE, OBJETIVO_GENERAL, OBJETIVO_ESPECIFICO, LINEA, ACCION)

#: Un id que ningún repositorio ha repartido ni va a repartir.
INEXISTENTE = 10**9


@dataclass
class Arbol:
    """El repositorio bajo prueba y lo que hace falta para sembrarle versiones."""

    repo: StrategicTreeRepository
    nueva_version: Callable[[], Awaitable[int]]
    #: La conexión de la variante PostgreSQL; `None` en memoria.
    conexion: AsyncConnection | None = None


def _arbol_en_memoria() -> Arbol:
    versiones = count(1)

    async def nueva_version() -> int:
        # La memoria no tiene tabla de versiones: cualquier entero hace de id.
        return next(versiones)

    return Arbol(repo=InMemoryStrategicTreeRepository(), nueva_version=nueva_version)


@asynccontextmanager
async def _arbol_en_postgresql():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada")
    motor = create_async_engine(url)
    try:
        async with motor.connect() as conexion:
            transaccion = await conexion.begin()
            # `create_savepoint`: el `commit()` de cada operación del repositorio
            # libera un SAVEPOINT en vez de cerrar la transacción de la
            # conexión, y el `rollback()` de abajo se lleva todo.
            fabrica = async_sessionmaker(
                bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )

            async def nueva_version() -> int:
                async with fabrica() as sesion:
                    instrumento = InstrumentModel(nombre=f"Instrumento de prueba {uuid4().hex[:8]}")
                    sesion.add(instrumento)
                    await sesion.flush()
                    version = InstrumentVersionModel(
                        instrumento_id=instrumento.id,
                        etiqueta="V1",
                        vigente_desde=date(2025, 1, 1),
                    )
                    sesion.add(version)
                    await sesion.flush()
                    id_version = version.id
                    await sesion.commit()
                return id_version

            try:
                yield Arbol(
                    repo=SqlAlchemyStrategicTreeRepository(fabrica),
                    nueva_version=nueva_version,
                    conexion=conexion,
                )
            finally:
                await transaccion.rollback()
    finally:
        await motor.dispose()


@pytest.fixture(params=["memoria", "postgresql"])
async def arbol(request):
    if request.param == "memoria":
        yield _arbol_en_memoria()
    else:
        async with _arbol_en_postgresql() as en_postgresql:
            yield en_postgresql


@pytest.fixture
async def arbol_postgresql():
    async with _arbol_en_postgresql() as en_postgresql:
        yield en_postgresql


async def _nodo(
    arbol: Arbol,
    version: int,
    clave: str,
    nivel: NodeKind,
    *,
    padre: StrategicNode | None = None,
    orden: int = 1,
    nombre: str | None = None,
) -> StrategicNode:
    nodo = StrategicNode(
        version_id=version,
        parent_id=padre.id if padre else None,
        kind=nivel,
        key=clave,
        name=nombre if nombre is not None else f"Denominación de {clave}",
        order=orden,
    )
    await arbol.repo.add(nodo)
    return nodo


async def _cadena(arbol: Arbol, version: int, claves: tuple[str, ...]) -> list[StrategicNode]:
    """Un nodo por clave, uno por nivel desde el eje, cada uno colgando del
    anterior, de arriba a abajo. Con menos de cinco claves la cadena se queda
    en el nivel que alcanza."""
    assert len(claves) <= len(NIVELES)
    nodos: list[StrategicNode] = []
    for nivel, clave in zip(NIVELES, claves, strict=False):
        nodos.append(await _nodo(arbol, version, clave, nivel, padre=nodos[-1] if nodos else None))
    return nodos


async def _ids(arbol: Arbol, version: int, **opciones) -> list[int]:
    return [n.id for n in await arbol.repo.list_tree(version, **opciones)]


# --------------------------------------------------------------------------- #
# Los niveles
# --------------------------------------------------------------------------- #


def test_los_niveles_son_los_cinco_del_check_en_su_orden_jerarquico():
    """Las cadenas son las que el `CHECK` de la migración 0038 admite, tal cual:
    el adaptador SQL escribe `nivel.value`, y una que el `CHECK` no conozca
    levantaría un error de la base en la primera inserción. El orden de
    definición es el jerárquico."""
    assert [nivel.value for nivel in NodeKind] == [
        "eje",
        "objetivo_general",
        "objetivo_especifico",
        "linea_estrategica",
        "accion",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("nivel", NIVELES)
async def test_cada_nivel_se_guarda_y_se_lee_como_el_mismo_nivel(arbol, nivel):
    """Uno por uno: con el `CHECK` de PostgreSQL de por medio, un valor del enum
    que la base no admite sólo se descubre al insertarlo, y una prueba en bloque
    lo vería igual de verde si el que falla no fuera el que se mira."""
    version = await arbol.nueva_version()
    nodo = await _nodo(arbol, version, "1", nivel)

    leido = await arbol.repo.get_by_id(nodo.id)
    assert leido is not None
    assert leido.kind is nivel


@pytest.mark.asyncio
@pytest.mark.parametrize("ajeno", ["meta", "Eje", "EJE", "linea", "", None])
async def test_un_nivel_que_el_pide_no_usa_no_se_guarda(arbol, ajeno):
    """El `CHECK` de PostgreSQL no existe en memoria, así que el dominio tiene
    que decir lo mismo: de lo contrario la memoria guardaría lo que la base
    rechaza. Las mayúsculas y «linea» (sin «_estrategica») cuentan: una
    coerción que ignore mayúsculas o acepte prefijos las dejaría pasar. Se
    prueba al agregar y al actualizar, que son las dos formas de dejar un nivel
    ajeno en el árbol."""
    version = await arbol.nueva_version()
    guardado = await _nodo(arbol, version, "1", EJE)

    with pytest.raises(ValidationError, match="nivel"):
        await arbol.repo.add(
            StrategicNode(
                version_id=version, parent_id=None, kind=ajeno, key="2", name="Ajeno", order=2
            )
        )
    with pytest.raises(ValidationError, match="nivel"):
        await arbol.repo.update(replace(guardado, kind=ajeno))

    # Ni el nodo nuevo entró ni el viejo cambió.
    assert await arbol.repo.list_tree(version, include_inactive=True) == [guardado]


@pytest.mark.asyncio
async def test_el_nivel_llega_como_texto_y_se_guarda_como_nivel(arbol):
    """Quien lee el nivel de un JSON lo tiene como cadena. Si la memoria la
    guardara tal cual, devolvería una `str` donde la base devuelve un
    `NodeKind`, y `n.kind is EJE` daría distinto en cada adaptador."""
    version = await arbol.nueva_version()
    nodo = StrategicNode(
        version_id=version, parent_id=None, kind="accion", key="1", name="Desde JSON", order=1
    )
    await arbol.repo.add(nodo)

    assert (await arbol.repo.get_by_id(nodo.id)).kind is ACCION


# --------------------------------------------------------------------------- #
# La clave y la denominación
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("clave", ["E1.L2.A3", "1.1.1.1.1", "12.10.11.13.14", "1.a", "A"])
async def test_la_clave_no_exige_formato_y_se_guarda_tal_cual(arbol, clave):
    """La fija el documento fuente y no tiene formato. Los valores son los que
    una regla de formato típica dejaría fuera: letras mezcladas con dígitos
    («E1.L2.A3»), los cinco segmentos del capítulo VII con segmentos de dos
    dígitos, una letra minúscula tras el punto («1.a») y una clave de un solo
    carácter sin puntos («A»). La clave del nodo no contiene la de su padre
    («9»)."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "9", EJE)
    nodo = await _nodo(arbol, version, clave, OBJETIVO_GENERAL, padre=eje)

    assert (await arbol.repo.get_by_id(nodo.id)).key == clave


@pytest.mark.asyncio
async def test_la_clave_cabe_en_cincuenta_caracteres_y_no_en_cincuenta_y_uno(arbol):
    """`clave` es `VARCHAR(50)`: en PostgreSQL una de 51 revienta con un error de
    la base, y en memoria entraría sin protesta. El 50 exacto entra en las dos
    -una regla «menos de 50» lo rechazaría-."""
    version = await arbol.nueva_version()
    await _nodo(arbol, version, "x" * 50, EJE)

    with pytest.raises(ValidationError, match="clave"):
        await _nodo(arbol, version, "x" * 51, EJE)


@pytest.mark.asyncio
@pytest.mark.parametrize("vacia", ["", "   "])
async def test_la_clave_y_la_denominacion_no_pueden_estar_vacias(arbol, vacia):
    """PostgreSQL acepta la cadena vacía en una columna NOT NULL, así que la
    base no lo impide y tiene que hacerlo el dominio. El valor en blanco («   »)
    cuenta como vacío: una regla `if not key` sólo cazaría la cadena vacía."""
    version = await arbol.nueva_version()

    with pytest.raises(ValidationError, match="clave"):
        await _nodo(arbol, version, vacia, EJE)
    with pytest.raises(ValidationError, match="denominación"):
        await _nodo(arbol, version, "1", EJE, nombre=vacia)

    assert await arbol.repo.list_tree(version, include_inactive=True) == []


# --------------------------------------------------------------------------- #
# Lo que se guarda y lo que se entrega
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_un_nodo_guardado_se_lee_con_cada_campo_en_su_sitio(arbol):
    """Todos los campos con valores distintos entre sí, para que una columna
    cambiada por otra -clave por denominación, orden por id, versión por
    padre- no pase: con `orden=1` y `clave="1"` por todas partes, un
    intercambio daría el mismo nodo. Entra inactivo a propósito: un nodo que
    ignora `is_active` al guardar nacería activo."""
    # Tres versiones de relleno: con una sola, el id de la versión sería 1, el
    # del padre también, y una columna cambiada por la otra no se notaría.
    for _ in range(3):
        await arbol.nueva_version()
    version = await arbol.nueva_version()
    padre = await _nodo(arbol, version, "P-1", EJE, orden=5)
    nodo = StrategicNode(
        version_id=version,
        parent_id=padre.id,
        kind=LINEA,
        key="K-7.3",
        name="Fomentar la vinculación — años 2025–2030, ñandú",
        order=42,
        is_active=False,
    )
    await arbol.repo.add(nodo)

    assert nodo.id > 0 and nodo.id != padre.id
    assert await arbol.repo.get_by_id(nodo.id) == nodo
    assert await arbol.repo.get_by_id(INEXISTENTE) is None


@pytest.mark.asyncio
async def test_lo_que_el_repositorio_entrega_no_es_lo_que_guarda(arbol):
    """Una base entrega filas nuevas en cada lectura; la memoria, si guardara los
    mismos objetos, dejaría que quien los toma cambie el árbol sin pasar por
    `update`. Se prueba con las cinco formas en que un objeto sale o entra: el
    que se pasó a `add`, el de `get_by_id`, los de `list_tree`, los de
    `ancestors` y el que se pasó a `update`.

    Después de **cada** una se mira el árbol, no al final: el `update` del
    último paso reemplaza el nodo guardado por un objeto nuevo y borraría el
    rastro de haber guardado, antes, el mismo objeto que se le dio a `add`.
    """
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE, nombre="Eje original")
    hijo = await _nodo(arbol, version, "1.1", OBJETIVO_GENERAL, padre=eje, nombre="Hijo original")

    async def nombres() -> list[str]:
        return [n.name for n in await arbol.repo.list_tree(version)]

    intacto = ["Eje original", "Hijo original"]

    hijo.name = "tocado después de add"
    assert await nombres() == intacto

    (await arbol.repo.get_by_id(hijo.id)).name = "tocado después de get_by_id"
    assert await nombres() == intacto

    for nodo in await arbol.repo.list_tree(version):
        nodo.name = "tocado después de list_tree"
        nodo.is_active = False
    assert await nombres() == intacto

    for ancestro in await arbol.repo.ancestors(hijo.id):
        ancestro.name = "tocado después de ancestors"
    assert await nombres() == intacto

    editado = replace(hijo, name="Hijo editado")
    await arbol.repo.update(editado)
    editado.name = "tocado después de update"
    assert await nombres() == ["Eje original", "Hijo editado"]


# --------------------------------------------------------------------------- #
# Los ancestros
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_los_ancestros_se_consultan_no_se_parsean(arbol):
    """La acción «E1.L2.A3» cuelga de una línea cuya clave («M») no la contiene.

    Un árbol señuelo, creado antes (ids menores), lleva justo los prefijos de la
    clave de la acción: «E1» y «E1.L2». Quien parta la clave y busque esos
    prefijos encuentra al señuelo y no a los ancestros reales, y quien tome «el
    primer nodo de cada nivel» de la versión también. Se compara por id y por
    nodo completo, no sólo por nivel: los niveles del señuelo podrían coincidir.
    """
    version = await arbol.nueva_version()
    senuelo_eje = await _nodo(arbol, version, "E1", EJE)
    await _nodo(arbol, version, "E1.L2", OBJETIVO_GENERAL, padre=senuelo_eje)
    eje, general, especifico, linea = await _cadena(arbol, version, ("7", "Q", "R.9", "M"))
    accion = await _nodo(arbol, version, "E1.L2.A3", ACCION, padre=linea)

    ancestros = await arbol.repo.ancestors(accion.id)

    assert [n.id for n in ancestros] == [eje.id, general.id, especifico.id, linea.id]
    assert [n.kind for n in ancestros] == [EJE, OBJETIVO_GENERAL, OBJETIVO_ESPECIFICO, LINEA]
    assert ancestros == [eje, general, especifico, linea]


@pytest.mark.asyncio
async def test_un_eje_no_tiene_ancestros_y_un_nodo_que_no_existe_no_es_un_eje(arbol):
    """Los dos casos dan «nada que listar» si se mira sólo la lista, y son cosas
    distintas: el primero es una respuesta; el segundo, un id equivocado. Una
    implementación que devuelva `[]` para ambos esconde el error de quien
    preguntó por un nodo que no existe."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)

    assert await arbol.repo.ancestors(eje.id) == []
    with pytest.raises(ResourceNotFoundError):
        await arbol.repo.ancestors(INEXISTENTE)


# --------------------------------------------------------------------------- #
# El orden de recorrido
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_el_arbol_se_lista_en_orden_de_recorrido_y_la_clave_no_ordena(arbol):
    """Padre, luego sus hijos en `orden`, cada uno con su propia descendencia
    antes del siguiente hermano. Los datos descartan cada regla equivocada:

    - Ejes sembrados con claves «10», «9», «2», `orden` 2, 1, 3 y nombres «B»,
      «C», «A». Por id sale 10, 9, 2; por clave como texto, 10, 2, 9; por clave
      numérica, 2, 9, 10; por nombre, 2, 10, 9. Sólo `orden` da 9, 10, 2.
    - Bajo el eje «9», dos hijos con `orden` 2 y 1 sembrados en ese orden: por id
      saldría al revés.
    - Bajo el eje «10», dos hijos con el **mismo** `orden` sembrados «z» y luego
      «a»: el desempate es el id -la inserción-, no la clave.
    - Cada eje tiene hijos: un recorrido por niveles pondría los tres ejes
      juntos antes que cualquier hijo.
    - Una segunda versión repite todas las claves: sin filtrar por versión
      aparecerían sus nodos.
    """
    version = await arbol.nueva_version()
    otra = await arbol.nueva_version()

    diez = await _nodo(arbol, version, "10", EJE, orden=2, nombre="B")
    nueve = await _nodo(arbol, version, "9", EJE, orden=1, nombre="C")
    dos = await _nodo(arbol, version, "2", EJE, orden=3, nombre="A")

    nueve_uno = await _nodo(arbol, version, "9.1", OBJETIVO_GENERAL, padre=nueve, orden=2)
    nueve_dos = await _nodo(arbol, version, "9.2", OBJETIVO_GENERAL, padre=nueve, orden=1)
    nieto = await _nodo(arbol, version, "9.2.1", OBJETIVO_ESPECIFICO, padre=nueve_dos)

    z = await _nodo(arbol, version, "z", OBJETIVO_GENERAL, padre=diez, orden=1)
    a = await _nodo(arbol, version, "a", OBJETIVO_GENERAL, padre=diez, orden=1)

    dos_uno = await _nodo(arbol, version, "2.1", OBJETIVO_GENERAL, padre=dos)

    # Otra versión con las mismas claves, sembrada a media carrera.
    for clave in ("10", "9", "2"):
        await _nodo(arbol, otra, clave, EJE)

    assert await arbol.repo.list_tree(version) == [
        nueve,
        nueve_dos,
        nieto,
        nueve_uno,
        diez,
        z,
        a,
        dos,
        dos_uno,
    ]


@pytest.mark.asyncio
async def test_lo_retirado_sale_del_listado_normal_pero_no_arrastra_lo_que_cuelga_de_el(arbol):
    """«Retirarlo no afecta a lo que ya cuelga de él»: la acción de una línea
    retirada sigue activa, así que sigue en el listado, en el lugar que le
    toca. Tres reglas equivocadas lo delatan:

    - desactivar en cascada: la acción desaparecería;
    - filtrar **antes** de recorrer: la acción quedaría sin padre y, según el
      recorrido, desaparece o sube a la raíz y sale al final;
    - no filtrar: la línea retirada seguiría saliendo.

    La segunda línea, hermana de la retirada, va después de la acción: si la
    acción subiera a la raíz o se perdiera, el orden cambiaría.
    """
    version = await arbol.nueva_version()
    eje, general, especifico, linea = await _cadena(arbol, version, ("1", "1.1", "1.1.1", "L"))
    accion = await _nodo(arbol, version, "A", ACCION, padre=linea)
    hermana = await _nodo(arbol, version, "L2", LINEA, padre=especifico, orden=2)

    await arbol.repo.deactivate(linea.id)

    assert await _ids(arbol, version) == [eje.id, general.id, especifico.id, accion.id, hermana.id]
    assert await _ids(arbol, version, include_inactive=True) == [
        eje.id,
        general.id,
        especifico.id,
        linea.id,
        accion.id,
        hermana.id,
    ]


# --------------------------------------------------------------------------- #
# Desactivar: no se borra, se retira
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_desactivar_no_borra_y_el_nodo_sigue_legible(arbol):
    """El nodo retirado sigue en la base, se lee por su id, sigue contando como
    ancestro de lo que cuelga de él y sólo él cambia: ni su padre, ni su hermano,
    ni su hijo, ni el nodo de otra versión con la misma clave.

    Reglas equivocadas que esto delata: borrar (desaparece de `include_inactive`
    y de `get_by_id`), desactivar por clave en vez de por id (cae el de la otra
    versión y el hermano homónimo de otro padre), desactivar a los vecinos, y
    filtrar los ancestros por activo (la acción perdería a su línea).
    """
    version = await arbol.nueva_version()
    otra = await arbol.nueva_version()
    eje, general, especifico, linea = await _cadena(arbol, version, ("1", "1.1", "1.1.1", "L"))
    accion = await _nodo(arbol, version, "A", ACCION, padre=linea)
    hermana = await _nodo(arbol, version, "L2", LINEA, padre=especifico, orden=2)
    homonima = await _nodo(arbol, otra, "L", LINEA)

    await arbol.repo.deactivate(linea.id)

    retirada = await arbol.repo.get_by_id(linea.id)
    assert retirada == replace(linea, is_active=False)
    assert [n.id for n in await arbol.repo.ancestors(accion.id)] == [
        eje.id,
        general.id,
        especifico.id,
        linea.id,
    ]
    for intacto in (eje, general, especifico, accion, hermana, homonima):
        assert await arbol.repo.get_by_id(intacto.id) == intacto


@pytest.mark.asyncio
async def test_desactivar_dos_veces_no_es_un_error_y_actualizar_vuelve_a_habilitar(arbol):
    """Retirar es idempotente. Y lo retirado se puede volver a habilitar con
    `update`: «no se borra» tiene sentido sólo si se puede deshacer. El nodo
    reactivado vuelve al listado normal."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)

    await arbol.repo.deactivate(eje.id)
    await arbol.repo.deactivate(eje.id)
    assert await _ids(arbol, version) == []

    await arbol.repo.update(replace(eje, is_active=True))
    assert await _ids(arbol, version) == [eje.id]


@pytest.mark.asyncio
async def test_desactivar_un_nodo_que_no_existe_es_un_error(arbol):
    """Un id equivocado no puede pasar por éxito: quien retira un nodo y no ve
    el error cree haberlo retirado."""
    with pytest.raises(ResourceNotFoundError):
        await arbol.repo.deactivate(INEXISTENTE)


# --------------------------------------------------------------------------- #
# El padre: que exista, que sea de la misma versión, que vaya más arriba en la
# cadena de niveles y que no forme un ciclo
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hijo", "padre"),
    [
        (ACCION, ACCION),
        (EJE, OBJETIVO_GENERAL),
        (OBJETIVO_GENERAL, OBJETIVO_ESPECIFICO),
        (OBJETIVO_ESPECIFICO, LINEA),
        (LINEA, ACCION),
        (EJE, ACCION),
    ],
    ids=["repite", "sube_uno", "sube_uno_mas", "sube_otro", "sube_el_ultimo", "sube_cuatro"],
)
async def test_el_nivel_del_hijo_va_mas_abajo_que_el_de_su_padre(arbol, hijo, padre):
    """Un eje colgando de una acción no es un árbol estratégico. Los seis casos
    son los que una regla floja dejaría pasar:

    - repetir el nivel (acción bajo acción), que una regla de «distinto del
      padre» caza pero una de «no más arriba» no;
    - cada par **adyacente al revés** -eje bajo objetivo general, objetivo
      general bajo específico, específico bajo línea, línea bajo acción-: una
      tabla de profundidades con dos niveles intercambiados pasa todos menos el
      par que intercambió, así que hacen falta los cuatro;
    - subir cuatro de golpe, que caza hasta la regla más floja.

    Se prueba al agregar y al mudar, que son las dos formas de colgar un nodo,
    y al final no queda nada escrito ni movido.
    """
    version = await arbol.nueva_version()
    raiz = await _nodo(arbol, version, "P", padre)
    suelto = await _nodo(arbol, version, "H", hijo, orden=2)

    with pytest.raises(ValidationError, match="no puede colgar de uno de nivel"):
        await _nodo(arbol, version, "N", hijo, padre=raiz)
    with pytest.raises(ValidationError, match="no puede colgar de uno de nivel"):
        await arbol.repo.update(replace(suelto, parent_id=raiz.id))

    assert await arbol.repo.list_tree(version, include_inactive=True) == [raiz, suelto]


@pytest.mark.asyncio
async def test_el_nivel_del_hijo_puede_saltarse_los_de_en_medio(arbol):
    """La contraparte, y lo que separa «más abajo» de «justo el siguiente»: el
    capítulo VII cuelga acciones de una línea sin objetivo específico de por
    medio, y una regla de «exactamente un nivel» perdería esas filas al cargar.

    Se salta al agregar -una acción directo del eje, tres niveles- y al mudar
    -esa acción a una línea, saltando uno-. La raíz entra con el nivel que
    traiga: es la única que no tiene padre con quien compararse.
    """
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)
    accion = await _nodo(arbol, version, "1.1", ACCION, padre=eje)
    linea = await _nodo(arbol, version, "1.2", LINEA, padre=eje, orden=2)
    raiz_que_no_es_eje = await _nodo(arbol, version, "2", OBJETIVO_ESPECIFICO, orden=2)

    await arbol.repo.update(replace(accion, parent_id=linea.id))

    assert await _ids(arbol, version) == [eje.id, linea.id, accion.id, raiz_que_no_es_eje.id]


@pytest.mark.asyncio
async def test_cambiar_el_nivel_de_un_nodo_mira_tambien_a_los_que_cuelgan_de_el(arbol):
    """La regla se olvida por abajo: al agregar y al mudar se mira al padre,
    pero un nodo que ya tiene hijos rompe la cadena cambiando de nivel él.

    Los dos hijos son líneas y uno está **retirado**: el mensaje dice «2», así
    que una regla que sólo mirara a los hijos activos se delata en el número.
    Que el eje pueda pasar a objetivo específico -más abajo, pero todavía por
    encima de sus líneas- descarta la regla de «un nodo con hijos no cambia de
    nivel», que pasaría los dos rechazos de arriba.
    """
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)
    await _nodo(arbol, version, "1.1", LINEA, padre=eje)
    retirada = await _nodo(arbol, version, "1.2", LINEA, padre=eje, orden=2)
    await arbol.repo.deactivate(retirada.id)

    with pytest.raises(ValidationError, match="2 de los nodos que cuelgan"):
        await arbol.repo.update(replace(eje, kind=LINEA))
    with pytest.raises(ValidationError, match="2 de los nodos que cuelgan"):
        await arbol.repo.update(replace(eje, kind=ACCION))

    await arbol.repo.update(replace(eje, kind=OBJETIVO_ESPECIFICO))
    assert (await arbol.repo.get_by_id(eje.id)).kind is OBJETIVO_ESPECIFICO


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quien", "bajo"),
    [(3, 3), (3, 4), (1, 3), (0, 4)],
    ids=["de_si_mismo", "de_su_hijo", "de_su_nieto", "la_raiz_de_su_tataranieto"],
)
async def test_un_nodo_no_puede_ser_su_propio_ancestro(arbol, quien, bajo):
    """Cadena eje(0) > general(1) > especifico(2) > linea(3) > accion(4). Cada
    caso cuelga a `quien` de un descendiente suyo, a una distancia distinta:

    - de sí mismo (0) -una regla «padre distinto del propio nodo» lo caza, y
      sólo eso-;
    - de su hijo (1) -una regla «el abuelo del nuevo padre no es el nodo» lo
      caza, y sólo eso-;
    - de su nieto (2) y de su tataranieto (4), que sólo caza quien sube hasta la
      raíz.

    Las claves de la cadena no se parecen entre sí. Y después del rechazo no
    queda nada cambiado: ni el nodo ni sus ancestros, porque una implementación
    que guarda y luego revisa deja el ciclo escrito.

    El mensaje es el de la revisión del ciclo y no el de la regla de nivel: en
    un árbol sano un descendiente va siempre más abajo que su ancestro, así que
    los cuatro casos rompen también esa regla y el orden en que el repositorio
    las pregunta decide cuál habla. Habla la del ciclo porque nombra el
    problema de verdad. Que la revisión del ciclo no sobra lo mide
    `test_el_ciclo_se_rechaza_aunque_el_nivel_ya_no_lo_impida`, donde la regla
    de nivel no alcanza.
    """
    version = await arbol.nueva_version()
    cadena = await _cadena(arbol, version, ("7", "Q", "R.9", "M", "x"))
    nodo, descendiente = cadena[quien], cadena[bajo]
    antes = await arbol.repo.list_tree(version)

    with pytest.raises(ValidationError, match="descendientes"):
        await arbol.repo.update(replace(nodo, parent_id=descendiente.id))

    assert await arbol.repo.list_tree(version) == antes


@pytest.mark.asyncio
async def test_un_nodo_se_puede_mudar_con_todo_lo_que_cuelga_de_el(arbol):
    """La contraparte de arriba: no todo cambio de padre es un ciclo. Se muda
    una línea con su acción a otro objetivo específico, y una acción a otra
    línea. Quien rechace cualquier cambio de padre, o lo guarde sin que los
    ancestros lo noten, falla aquí. Los ancestros nuevos son los del nuevo
    padre, no los viejos."""
    version = await arbol.nueva_version()
    eje, general, especifico, linea = await _cadena(arbol, version, ("1", "1.1", "1.1.1", "L"))
    accion = await _nodo(arbol, version, "A", ACCION, padre=linea)
    otro_especifico = await _nodo(
        arbol, version, "1.1.2", OBJETIVO_ESPECIFICO, padre=general, orden=2
    )
    otra_linea = await _nodo(arbol, version, "L2", LINEA, padre=otro_especifico)

    await arbol.repo.update(replace(linea, parent_id=otro_especifico.id))
    assert [n.id for n in await arbol.repo.ancestors(accion.id)] == [
        eje.id,
        general.id,
        otro_especifico.id,
        linea.id,
    ]

    await arbol.repo.update(replace(accion, parent_id=otra_linea.id))
    assert [n.id for n in await arbol.repo.ancestors(accion.id)] == [
        eje.id,
        general.id,
        otro_especifico.id,
        otra_linea.id,
    ]
    # La línea y la otra línea quedan como hermanas bajo el objetivo nuevo, con
    # el mismo `orden` -gana la que se sembró antes-, y la acción cuelga de la
    # segunda. El objetivo de origen se quedó sin hijos.
    assert await _ids(arbol, version) == [
        eje.id,
        general.id,
        especifico.id,
        otro_especifico.id,
        linea.id,
        otra_linea.id,
        accion.id,
    ]


@pytest.mark.asyncio
async def test_un_nodo_no_cuelga_de_un_padre_que_no_existe(arbol):
    """La foránea de PostgreSQL no está en memoria. Se prueba al agregar y al
    actualizar, y que no quede nada escrito."""
    version = await arbol.nueva_version()
    guardado = await _nodo(arbol, version, "1", EJE)

    with pytest.raises(ValidationError, match="padre"):
        await arbol.repo.add(
            StrategicNode(
                version_id=version,
                parent_id=INEXISTENTE,
                kind=OBJETIVO_GENERAL,
                key="1.1",
                name="Huérfano",
                order=1,
            )
        )
    with pytest.raises(ValidationError, match="padre"):
        await arbol.repo.update(replace(guardado, parent_id=INEXISTENTE))

    assert await arbol.repo.list_tree(version, include_inactive=True) == [guardado]


@pytest.mark.asyncio
async def test_un_nodo_no_cuelga_de_un_padre_de_otra_version(arbol):
    """El árbol de cada versión es suyo. El control está al final: el mismo hijo,
    en la versión del padre, sí entra -lo que falló antes fue la versión, no otra
    cosa de la fila-."""
    primera = await arbol.nueva_version()
    segunda = await arbol.nueva_version()
    eje = await _nodo(arbol, primera, "1", EJE)
    otro_eje = await _nodo(arbol, segunda, "5", EJE)

    with pytest.raises(ValidationError, match="otra versión"):
        await arbol.repo.add(
            StrategicNode(
                version_id=segunda,
                parent_id=eje.id,
                kind=OBJETIVO_GENERAL,
                key="1.1",
                name="Colgado de otra versión",
                order=1,
            )
        )
    with pytest.raises(ValidationError, match="otra versión"):
        await arbol.repo.update(replace(otro_eje, parent_id=eje.id))

    assert await arbol.repo.list_tree(segunda) == [otro_eje]
    await _nodo(arbol, primera, "1.1", OBJETIVO_GENERAL, padre=eje)


@pytest.mark.asyncio
async def test_un_nodo_no_cambia_de_version_al_actualizarse(arbol):
    """Cambiar `version_id` mudaría el nodo a otro árbol sin sus hijos. El nodo
    raíz no tiene padre que lo detenga, así que la regla es del propio nodo."""
    primera = await arbol.nueva_version()
    segunda = await arbol.nueva_version()
    eje = await _nodo(arbol, primera, "1", EJE)

    with pytest.raises(ValidationError, match="versión"):
        await arbol.repo.update(replace(eje, version_id=segunda))

    assert await arbol.repo.list_tree(primera) == [eje]
    assert await arbol.repo.list_tree(segunda) == []


# --------------------------------------------------------------------------- #
# Actualizar
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_actualizar_guarda_cada_campo_y_toca_solo_ese_nodo(arbol):
    """Cada campo editable cambia a un valor distinto de todos los demás, y se
    comprueba que el nodo de la otra versión con la misma clave y el hermano no
    se mueven: una actualización que filtra por clave en vez de por id los
    arrastra. El nivel cambia también -el nivel es un dato, no una posición-."""
    version = await arbol.nueva_version()
    otra = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)
    nodo = await _nodo(arbol, version, "1.1", OBJETIVO_GENERAL, padre=eje, orden=1)
    hermano = await _nodo(arbol, version, "1.2", OBJETIVO_GENERAL, padre=eje, orden=2)
    homonimo = await _nodo(arbol, otra, "1.1", OBJETIVO_GENERAL)

    editado = replace(
        nodo, kind=LINEA, key="L-9", name="Nuevo texto — con acento", order=77, is_active=False
    )
    await arbol.repo.update(editado)

    assert await arbol.repo.get_by_id(nodo.id) == editado
    for intacto in (eje, hermano, homonimo):
        assert await arbol.repo.get_by_id(intacto.id) == intacto


@pytest.mark.asyncio
async def test_actualizar_un_nodo_que_no_existe_es_un_error(arbol):
    """Un `update` sobre un id que no existe no puede crear el nodo ni pasar por
    éxito."""
    version = await arbol.nueva_version()
    fantasma = StrategicNode(
        id=INEXISTENTE, version_id=version, parent_id=None, kind=EJE, key="1", name="x", order=1
    )

    with pytest.raises(ResourceNotFoundError):
        await arbol.repo.update(fantasma)

    assert await arbol.repo.list_tree(version, include_inactive=True) == []


@pytest.mark.asyncio
async def test_actualizar_con_datos_ajenos_no_deja_nada_escrito(arbol):
    """Una actualización que revienta no puede dejar a medias lo que sí era
    válido: aquí el nombre es nuevo y legítimo, pero la clave llega vacía."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE, nombre="Original")

    with pytest.raises(ValidationError, match="clave"):
        await arbol.repo.update(replace(eje, name="Nuevo", key=""))

    assert await arbol.repo.get_by_id(eje.id) == eje


# --------------------------------------------------------------------------- #
# Hermanos: la clave no se repite
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dos_hermanos_no_repiten_clave(arbol):
    """Hermanos son los que comparten padre. El duplicado difiere en todo lo
    demás -nivel, denominación y orden-, para que la única razón por la que
    choque sea la clave: una regla que comparara más columnas lo dejaría pasar."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)
    await _nodo(arbol, version, "1.1", OBJETIVO_GENERAL, padre=eje, orden=1, nombre="Uno")

    with pytest.raises(ConflictError, match="clave"):
        await _nodo(arbol, version, "1.1", ACCION, padre=eje, orden=7, nombre="Otro texto")


@pytest.mark.asyncio
async def test_dos_ejes_de_la_misma_version_no_repiten_clave(arbol):
    """Los ejes no tienen padre, y comparar `padre_id` con `==` en SQL (o sólo
    cuando no es nulo) los dejaría repetirse: es el hueco que `NULLS NOT
    DISTINCT` cierra en la base y que la memoria tiene que cerrar por su
    cuenta."""
    version = await arbol.nueva_version()
    await _nodo(arbol, version, "1", EJE)

    with pytest.raises(ConflictError, match="clave"):
        await _nodo(arbol, version, "1", EJE, orden=2, nombre="Otro eje")


@pytest.mark.asyncio
async def test_la_misma_clave_cabe_bajo_otro_padre_y_en_otra_version(arbol):
    """La contraparte: la unicidad es entre hermanos de una versión, no más
    ancha. Una que valiera para toda la versión, o para toda la base, impediría
    cargar la versión siguiente del PIDE -que repite casi todas las claves-."""
    primera = await arbol.nueva_version()
    segunda = await arbol.nueva_version()
    eje_uno = await _nodo(arbol, primera, "1", EJE)
    eje_dos = await _nodo(arbol, primera, "2", EJE, orden=2)
    await _nodo(arbol, segunda, "1", EJE)
    await _nodo(arbol, primera, "1.1", OBJETIVO_GENERAL, padre=eje_uno)
    await _nodo(arbol, primera, "1.1", OBJETIVO_GENERAL, padre=eje_dos)

    assert len(await arbol.repo.list_tree(primera)) == 4
    assert len(await arbol.repo.list_tree(segunda)) == 1


@pytest.mark.asyncio
async def test_actualizar_no_choca_con_uno_mismo_pero_si_con_un_hermano(arbol):
    """Un nodo que se guarda sin cambiar de clave no es un duplicado de sí mismo.
    Y la unicidad se vigila tanto al cambiar de clave como al cambiar de padre:
    mudar un nodo a donde ya hay uno con su clave es el mismo choque."""
    version = await arbol.nueva_version()
    eje = await _nodo(arbol, version, "1", EJE)
    otro_eje = await _nodo(arbol, version, "2", EJE, orden=2)
    primero = await _nodo(arbol, version, "1.1", OBJETIVO_GENERAL, padre=eje, orden=1)
    await _nodo(arbol, version, "1.2", OBJETIVO_GENERAL, padre=eje, orden=2)
    del_otro = await _nodo(arbol, version, "1.1", OBJETIVO_GENERAL, padre=otro_eje)

    # Sin cambiar la clave: no choca con él mismo.
    await arbol.repo.update(replace(primero, name="Cambia sólo la denominación"))

    # Cambiando la clave a la de su hermano: choca.
    with pytest.raises(ConflictError, match="clave"):
        await arbol.repo.update(replace(primero, key="1.2"))

    # Mudándose a donde ya hay una «1.1»: choca.
    with pytest.raises(ConflictError, match="clave"):
        await arbol.repo.update(replace(del_otro, parent_id=eje.id))

    # Y mudándose con otra clave, no.
    await arbol.repo.update(replace(del_otro, parent_id=eje.id, key="1.3"))


# --------------------------------------------------------------------------- #
# Sólo PostgreSQL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_el_adaptador_sql_escribe_en_las_columnas_de_la_migracion(arbol_postgresql):
    """Las demás pruebas comparan lo que el repositorio devuelve con lo que se le
    dio, y un repositorio que escribiera en la columna equivocada y la leyera de
    la misma pasaría. Aquí se mira la fila con SQL crudo, columna por columna, y
    el nivel tal como lo guarda el `CHECK`."""
    arbol = arbol_postgresql
    version = await arbol.nueva_version()
    padre = await _nodo(arbol, version, "P", EJE)
    nodo = await _nodo(arbol, version, "K-7.3", LINEA, padre=padre, orden=42, nombre="Texto único")

    async def fila():
        return (
            await arbol.conexion.execute(
                text(
                    "SELECT version_id, padre_id, tipo, clave, denominacion, orden, activo "
                    "FROM nodos_estrategicos WHERE id = :id"
                ),
                {"id": nodo.id},
            )
        ).one()

    assert tuple(await fila()) == (
        version,
        padre.id,
        "linea_estrategica",
        "K-7.3",
        "Texto único",
        42,
        True,
    )

    await arbol.repo.deactivate(nodo.id)
    assert (await fila()).activo is False


@pytest.mark.asyncio
async def test_los_ancestros_terminan_aunque_la_base_tenga_un_ciclo(arbol_postgresql):
    """La base acepta un ciclo: la foránea compuesta sólo exige que el padre
    exista en la misma versión. El repositorio no deja crearlo, pero un UPDATE
    a mano sí, y un recursivo con `UNION ALL` sobre uno no termina nunca. Aquí
    se fabrica uno a mano y se exige que la consulta **termine** y diga que el
    árbol está mal, en vez de colgar la petición.

    Y que el listado **grite**, que es lo que esta prueba fijaba al revés. El
    ciclo es A↔B, pero de B cuelgan D y E, que no son parte de él: un listado
    que se limite a no girar devuelve sólo a C y pierde **cuatro** nodos que
    existen en la base. En un sistema que tiene que acreditar cifras ante una
    revisión externa, un nodo que existe y no aparece es lo peor que puede
    pasar; por eso el mensaje dice cuántos son y cuáles, y por eso la cuenta
    está en la aserción: un grito que sólo nombrara a los dos del ciclo
    escondería a D y a E igual que el silencio.

    `statement_timeout` es la red de la propia prueba: si la consulta no
    termina, que muera a los dos segundos con un error en vez de girar hasta
    llenar el disco de la base de pruebas con filas de un recursivo infinito.
    """
    arbol = arbol_postgresql
    version = await arbol.nueva_version()
    de_arriba = await _nodo(arbol, version, "A", EJE)
    de_abajo = await _nodo(arbol, version, "B", OBJETIVO_GENERAL, padre=de_arriba)
    colgado = await _nodo(arbol, version, "D", OBJETIVO_ESPECIFICO, padre=de_abajo)
    nieto = await _nodo(arbol, version, "E", LINEA, padre=colgado)
    ajeno = await _nodo(arbol, version, "C", EJE, orden=2)
    await arbol.conexion.execute(
        text("UPDATE nodos_estrategicos SET padre_id = :abajo WHERE id = :arriba"),
        {"abajo": de_abajo.id, "arriba": de_arriba.id},
    )
    await arbol.conexion.execute(text("SET LOCAL statement_timeout = '2s'"))

    with pytest.raises(InvalidStateError, match="ciclo"):
        await arbol.repo.ancestors(de_abajo.id)

    perdidos = ", ".join(
        str(identificador)
        for identificador in sorted((de_arriba.id, de_abajo.id, colgado.id, nieto.id))
    )
    with pytest.raises(InvalidStateError, match=f"4 nodos no se alcanzan.*{perdidos}"):
        await arbol.repo.list_tree(version)
    with pytest.raises(InvalidStateError, match="4 nodos no se alcanzan"):
        await arbol.repo.list_tree(version, include_inactive=True)

    # C existe y se lee por su id: lo que está mal es el listado del árbol, no
    # la versión entera.
    assert await arbol.repo.get_by_id(ajeno.id) == ajeno


@pytest.mark.asyncio
async def test_el_ciclo_se_rechaza_aunque_el_nivel_ya_no_lo_impida(arbol_postgresql):
    """La regla de nivel hace imposible el ciclo **mientras la cadena esté
    sana**: en un árbol donde cada hijo va más abajo que su padre, mudar un
    nodo bajo un descendiente suyo es siempre subir, y la regla lo rechaza. La
    revisión del ciclo parecería entonces inalcanzable; no lo es.

    Dos `update` simultáneos la rompen sin que ninguno de los dos sea inválido:
    uno muda B bajo A y el otro baja el nivel de A, cada uno mirando un estado
    donde el otro todavía no escribió -medido con una base desechable y las dos
    transacciones leyendo antes de que ninguna escribiera-. El resultado es un
    padre más abajo que su hijo, y desde ahí mudar A bajo B **cumple** la regla
    de nivel. Lo único que lo impide es esta revisión.

    Aquí ese estado se escribe con un `UPDATE` a mano, que es lo mismo que la
    carrera deja y no depende del reloj. Sólo PostgreSQL: en memoria no hay
    puerta para dejar la cadena rota, y una prueba que no puede llegar al
    estado no mide nada.
    """
    arbol = arbol_postgresql
    version = await arbol.nueva_version()
    de_arriba = await _nodo(arbol, version, "A", EJE)
    de_abajo = await _nodo(arbol, version, "B", OBJETIVO_GENERAL, padre=de_arriba)
    await arbol.conexion.execute(
        text("UPDATE nodos_estrategicos SET tipo = 'accion' WHERE id = :id"),
        {"id": de_arriba.id},
    )
    roto = await arbol.repo.get_by_id(de_arriba.id)
    assert roto.kind is ACCION

    with pytest.raises(ValidationError, match="descendientes"):
        await arbol.repo.update(replace(roto, parent_id=de_abajo.id))

    assert [n.id for n in await arbol.repo.ancestors(de_abajo.id)] == [de_arriba.id]
    assert await _ids(arbol, version, include_inactive=True) == [de_arriba.id, de_abajo.id]


@pytest.mark.asyncio
async def test_una_version_que_no_existe_no_recibe_nodos(arbol_postgresql):
    """La memoria no tiene tabla de versiones y no puede saberlo; PostgreSQL sí,
    y su foránea tiene que llegar como un error del dominio y no como un
    `IntegrityError` pelado que la API vería como un 500. Es una raíz, para que
    la rechace la foránea de la versión y no la comprobación del padre."""
    arbol = arbol_postgresql

    with pytest.raises(ValidationError, match="versión"):
        await _nodo(arbol, INEXISTENTE, "1", EJE)
