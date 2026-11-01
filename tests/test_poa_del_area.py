from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from itertools import count
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.entities import User
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.repository import InMemoryUserRepository
from app.modules.institutional_catalogs.domain.entities import Area
from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
)
from app.modules.institutional_catalogs.infrastructure.repository import InMemoryAreaRepository
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyAreaRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_repository import (
    InMemoryStrategicTreeRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)
from app.modules.poa_institucional.application.use_cases.manage_poa_area import (
    OpenPoaArea,
    OpenPoaAreaCommand,
    SaveActivityCommand,
    SavePoaActivity,
    SubmitPoaArea,
    SubmitPoaAreaCommand,
)
from app.modules.poa_institucional.domain.entities import (
    MESES_DEL_EJERCICIO,
    META_MAS_ALTA_QUE_CABE,
    Activity,
    MonthlyTarget,
    PoaArea,
    PoaAreaStatus,
    whats_missing_to_submit,
)
from app.modules.poa_institucional.domain.ports.area_leadership import AreaLeadership
from app.modules.poa_institucional.domain.ports.repositories import PoaAreaRepository
from app.modules.poa_institucional.infrastructure.repository import (
    InMemoryAreaLeadership,
    InMemoryPoaAreaRepository,
)
from app.modules.poa_institucional.infrastructure.sql_repository import (
    SqlAlchemyAreaLeadership,
    SqlAlchemyPoaAreaRepository,
)
from app.modules.poa_planning.domain.entities import PoaExercise
from app.modules.poa_planning.domain.ports.repositories import PoaRepository
from app.modules.poa_planning.infrastructure.repository import InMemoryPoaRepository
from app.modules.poa_planning.infrastructure.sql_repository import SqlAlchemyPoaRepository
from app.shared.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ResourceNotFoundError,
    ValidationError,
)
from app.shared.domain.value_objects import Email

INEXISTENTE = 10**9

DOCE_METAS_DESIGUALES_QUE_SUMAN_24 = (
    Decimal(1),
    Decimal(3),
    Decimal(0),
    Decimal(2),
    Decimal(5),
    Decimal(1),
    Decimal(4),
    Decimal(0),
    Decimal(2),
    Decimal(1),
    Decimal(3),
    Decimal(2),
)

DOCE_METAS_DESIGUALES_QUE_SUMAN_22 = DOCE_METAS_DESIGUALES_QUE_SUMAN_24[:-1] + (Decimal(0),)

DOCE_METAS_DESIGUALES_QUE_SUMAN_30 = DOCE_METAS_DESIGUALES_QUE_SUMAN_24[:-1] + (Decimal(8),)

ONCE_METAS_DESIGUALES_QUE_SUMAN_24_Y_UN_DOCEAVO_EN_CERO = DOCE_METAS_DESIGUALES_QUE_SUMAN_24[
    :10
] + (Decimal(5), Decimal(0))

ONCE_METAS_DESIGUALES_QUE_SUMAN_22_Y_UN_DOCEAVO_EN_CERO = DOCE_METAS_DESIGUALES_QUE_SUMAN_24[
    :10
] + (Decimal(3), Decimal(0))


@dataclass
class Tablero:
    repo: PoaAreaRepository
    arbol: StrategicTreeRepository
    liderazgo: AreaLeadership
    ejercicios: PoaRepository
    areas: AreaRepository
    nuevo_ejercicio: Callable[[], Awaitable[int]]
    nueva_area: Callable[[], Awaitable[int]]
    nueva_unidad: Callable[[], Awaitable[int]]
    nueva_version: Callable[[], Awaitable[int]]
    dar_responsable: Callable[[int], Awaitable[None]]
    nuevo_usuario: Callable[..., Awaitable[int]]
    conexion: AsyncConnection | None = None

    def abrir(self) -> OpenPoaArea:
        return OpenPoaArea(self.repo, self.ejercicios, self.areas)

    def guardar(self) -> SavePoaActivity:
        return SavePoaActivity(self.repo, self.arbol)

    def enviar(self) -> SubmitPoaArea:
        return SubmitPoaArea(self.repo, self.liderazgo)


def _tablero_en_memoria() -> Tablero:
    unidades = count(1)
    versiones = count(1)
    anios = count(2000)

    usuarios = InMemoryUserRepository()
    ejercicios = InMemoryPoaRepository()
    areas = InMemoryAreaRepository()

    async def siguiente(contador) -> int:
        return next(contador)

    async def nuevo_ejercicio() -> int:
        ejercicio = PoaExercise.create(next(anios), catalog_id=1)
        await ejercicios.add_exercise(ejercicio)
        return ejercicio.id

    async def nueva_area() -> int:
        area = Area.create(code=f"PRUEBA-{uuid4().hex[:8]}", name=f"Área {uuid4().hex[:8]}")
        await areas.add(area)
        return area.id

    async def nuevo_usuario(area_id: int, rol: str | None, *, activo: bool = True) -> int:
        usuario = User(
            email=Email(f"persona-{uuid4().hex}@upchiapas.edu.mx"),
            full_name="Persona de prueba",
            password_hash="$argon2id$de$prueba",
            roles=frozenset() if rol is None else frozenset({Role(rol)}),
            area_id=area_id,
            is_active=activo,
        )
        await usuarios.add(usuario)
        return usuario.id

    async def dar_responsable(area_id: int) -> None:
        await nuevo_usuario(area_id, Role.RESPONSABLE_AREA.value)

    return Tablero(
        repo=InMemoryPoaAreaRepository(),
        arbol=InMemoryStrategicTreeRepository(),
        liderazgo=InMemoryAreaLeadership(usuarios),
        ejercicios=ejercicios,
        areas=areas,
        nuevo_ejercicio=nuevo_ejercicio,
        nueva_area=nueva_area,
        nueva_unidad=lambda: siguiente(unidades),
        nueva_version=lambda: siguiente(versiones),
        dar_responsable=dar_responsable,
        nuevo_usuario=nuevo_usuario,
    )


async def _insertar_sin_id(conexion: AsyncConnection, tabla: str, **valores) -> None:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    await conexion.execute(text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores})"), valores)


async def _insertar(conexion: AsyncConnection, tabla: str, **valores) -> int:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    return (
        await conexion.execute(
            text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores}) RETURNING id"),
            valores,
        )
    ).scalar_one()


@asynccontextmanager
async def _tablero_en_postgresql():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada")
    motor = create_async_engine(url)
    try:
        async with motor.connect() as conexion:
            transaccion = await conexion.begin()
            fabrica = async_sessionmaker(
                bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )

            async def nuevo_ejercicio() -> int:
                anio = (
                    await conexion.execute(
                        text(
                            "SELECT min(anio) FROM generate_series(2000, 2200) AS anio "
                            "WHERE anio NOT IN (SELECT anio FROM poa_ejercicios)"
                        )
                    )
                ).scalar_one()
                catalogo = await _insertar(
                    conexion, "poa_catalogos", nombre=f"POA de prueba {uuid4().hex}", anio=anio
                )
                return await _insertar(conexion, "poa_ejercicios", anio=anio, catalogo_id=catalogo)

            async def nueva_area() -> int:
                return await _insertar(conexion, "areas", nombre=f"Área de prueba {uuid4().hex}")

            async def nueva_unidad() -> int:
                return await _insertar(
                    conexion,
                    "unidades_medida",
                    clave=f"prueba-{uuid4().hex[:20]}",
                    nombre="Unidad de prueba",
                    plural="Unidades de prueba",
                )

            async def nueva_version() -> int:
                instrumento = await _insertar(
                    conexion, "instrumentos", nombre=f"Instrumento de prueba {uuid4().hex[:20]}"
                )
                return await _insertar(
                    conexion,
                    "instrumento_versiones",
                    instrumento_id=instrumento,
                    etiqueta="V1",
                    vigente_desde=date(2025, 1, 1),
                )

            async def nuevo_usuario(area_id: int, rol: str | None, *, activo: bool = True) -> int:
                usuario = await _insertar(
                    conexion,
                    "usuarios",
                    nombre="Persona de prueba",
                    correo=f"persona-{uuid4().hex}@upchiapas.edu.mx",
                    hash_password="$argon2id$de$prueba",
                    area_id=area_id,
                    activo=activo,
                )
                if rol is not None:
                    await _insertar_sin_id(conexion, "usuario_roles", usuario_id=usuario, rol=rol)
                return usuario

            async def dar_responsable(area_id: int) -> None:
                await nuevo_usuario(area_id, Role.RESPONSABLE_AREA.value)

            try:
                yield Tablero(
                    repo=SqlAlchemyPoaAreaRepository(fabrica),
                    arbol=SqlAlchemyStrategicTreeRepository(fabrica),
                    liderazgo=SqlAlchemyAreaLeadership(fabrica),
                    ejercicios=SqlAlchemyPoaRepository(fabrica),
                    areas=SqlAlchemyAreaRepository(fabrica),
                    nuevo_ejercicio=nuevo_ejercicio,
                    nueva_area=nueva_area,
                    nueva_unidad=nueva_unidad,
                    nueva_version=nueva_version,
                    dar_responsable=dar_responsable,
                    conexion=conexion,
                    nuevo_usuario=nuevo_usuario,
                )
            finally:
                await transaccion.rollback()
    finally:
        await motor.dispose()


@pytest.fixture(params=["memoria", "postgresql"])
async def tablero(request):
    if request.param == "memoria":
        yield _tablero_en_memoria()
    else:
        async with _tablero_en_postgresql() as en_postgresql:
            yield en_postgresql


@pytest.fixture
async def tablero_postgresql():
    async with _tablero_en_postgresql() as en_postgresql:
        yield en_postgresql


async def _poa_area(tablero: Tablero, *, con_responsable: bool = True) -> PoaArea:
    area = await tablero.nueva_area()
    if con_responsable:
        await tablero.dar_responsable(area)
    return await tablero.abrir().execute(
        OpenPoaAreaCommand(exercise_id=await tablero.nuevo_ejercicio(), area_id=area)
    )


async def _nodo_raiz(
    tablero: Tablero, nivel: NodeKind = NodeKind.ACCION, *, activo: bool = True
) -> int:
    nodo = StrategicNode(
        version_id=await tablero.nueva_version(),
        parent_id=None,
        kind=nivel,
        key=f"{nivel.value}-{uuid4().hex[:8]}",
        name=f"Nodo de prueba {nivel.value}",
        order=1,
    )
    await tablero.arbol.add(nodo)
    if not activo:
        await tablero.arbol.deactivate(nodo.id)
    return nodo.id


def _programacion(
    metas: tuple[Decimal, ...], *, sin_incluir: tuple[int, ...] = ()
) -> list[MonthlyTarget]:
    return [
        MonthlyTarget(
            month=mes,
            target=Decimal(0) if mes in sin_incluir else metas[mes - 1],
            included=mes not in sin_incluir,
        )
        for mes in MESES_DEL_EJERCICIO
    ]


async def _actividad_completa(
    tablero: Tablero,
    poa_area: PoaArea,
    *,
    nombre: str = "Impartir el taller de titulación",
    meta_anual: Decimal = Decimal(24),
    metas: tuple[Decimal, ...] = DOCE_METAS_DESIGUALES_QUE_SUMAN_24,
    sin_incluir: tuple[int, ...] = (),
    nodo_id: int | None = None,
) -> Activity:
    return await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name=nombre,
            node_id=nodo_id if nodo_id is not None else await _nodo_raiz(tablero),
            unit_id=await tablero.nueva_unidad(),
            evaluation_method="Listas de asistencia",
            annual_target=meta_anual,
            monthly=_programacion(metas, sin_incluir=sin_incluir),
        )
    )


def test_los_estados_del_poa_del_area_son_exactamente_los_dos_del_check_cerrado():
    assert [estado.value for estado in PoaAreaStatus] == ["borrador", "enviado"]


async def test_un_borrador_incompleto_se_guarda_con_solo_su_denominacion(tablero):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Apenas empezada")
    )

    leida = await tablero.repo.get_activity(guardada.id)
    assert (leida.node_id, leida.unit_id, leida.evaluation_method, leida.annual_target) == (
        None,
        None,
        None,
        None,
    )
    assert leida.monthly == []
    assert (leida.name, leida.version, leida.is_active) == ("Apenas empezada", 1, True)


async def test_un_poa_de_area_nace_en_borrador_y_el_segundo_llamado_devuelve_el_mismo(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.nueva_area()

    primero = await tablero.abrir().execute(OpenPoaAreaCommand(exercise_id=ejercicio, area_id=area))
    segundo = await tablero.abrir().execute(OpenPoaAreaCommand(exercise_id=ejercicio, area_id=area))

    assert primero.status is PoaAreaStatus.BORRADOR
    assert primero.version == 1
    assert segundo.id == primero.id


INVISIBLES_QUE_DEJA_COPIAR_DE_UN_PDF = {
    "espacio_de_ancho_cero": "\u200b",
    "marca_de_orden_de_bytes": "\ufeff",
    "guion_blando": "\u00ad",
}

POR_INVISIBLE = pytest.mark.parametrize(
    "invisible",
    INVISIBLES_QUE_DEJA_COPIAR_DE_UN_PDF.values(),
    ids=INVISIBLES_QUE_DEJA_COPIAR_DE_UN_PDF.keys(),
)


async def test_la_denominacion_de_una_actividad_es_obligatoria(tablero):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="denominación"):
        await tablero.guardar().execute(SaveActivityCommand(poa_area_id=poa_area.id, name="   "))


@POR_INVISIBLE
async def test_una_denominacion_de_solo_invisibles_cuenta_como_vacia(tablero, invisible):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="denominación"):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name=f" {invisible} ")
        )

    assert await tablero.repo.list_activities(poa_area.id) == []


@POR_INVISIBLE
async def test_un_invisible_no_entra_en_la_denominacion_ni_en_el_metodo(tablero, invisible):
    poa_area = await _poa_area(tablero)

    actividad = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name=f" {invisible}Impartir{invisible} el taller{invisible} ",
            evaluation_method=f"{invisible}Listas{invisible} de asistencia{invisible}",
        )
    )

    guardada = (await tablero.repo.list_activities(poa_area.id))[0]
    assert (actividad.name, actividad.evaluation_method) == (
        "Impartir el taller",
        "Listas de asistencia",
    )
    assert (guardada.name, guardada.evaluation_method) == (
        "Impartir el taller",
        "Listas de asistencia",
    )


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        ("name", "denominación de la actividad no admite el carácter nulo"),
        ("evaluation_method", "método de evaluación no admite el carácter nulo"),
    ],
)
async def test_el_caracter_nulo_no_entra_ni_en_la_denominacion_ni_en_el_metodo(
    tablero, campo, esperado
):
    poa_area = await _poa_area(tablero)
    mandado = {"name": "Impartir el taller", campo: "Con el nulo\0 adentro"}

    with pytest.raises(ValidationError, match=esperado):
        await tablero.guardar().execute(SaveActivityCommand(poa_area_id=poa_area.id, **mandado))

    assert await tablero.repo.list_activities(poa_area.id) == []


@pytest.mark.parametrize("en_blanco", ["", "   "], ids=["vacio", "solo_espacios"])
async def test_un_metodo_de_evaluacion_en_blanco_se_guarda_como_no_puesto(tablero, en_blanco):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id, name="Con el método en blanco", evaluation_method=en_blanco
        )
    )

    assert guardada.evaluation_method is None
    assert (await tablero.repo.get_activity(guardada.id)).evaluation_method is None


def test_un_metodo_de_evaluacion_vacio_cuenta_como_lo_que_falta():
    sin_el_campo = Activity(poa_area_id=1, name="Sin método", evaluation_method=None)
    vacio = Activity(poa_area_id=1, name="Con el método vacío", evaluation_method="")

    assert "el método de evaluación" in whats_missing_to_submit(sin_el_campo)
    assert "el método de evaluación" in whats_missing_to_submit(vacio)


@pytest.mark.parametrize(
    "en_blanco",
    ["   ", "\t", "\n", *INVISIBLES_QUE_DEJA_COPIAR_DE_UN_PDF.values()],
    ids=["espacios", "tabulador", "salto", *INVISIBLES_QUE_DEJA_COPIAR_DE_UN_PDF],
)
def test_un_metodo_de_evaluacion_de_puros_invisibles_tambien_cuenta_como_lo_que_falta(en_blanco):
    escrita_por_fuera = Activity(
        poa_area_id=1, name="Con el método en blanco", evaluation_method=en_blanco
    )

    assert "el método de evaluación" in whats_missing_to_submit(escrita_por_fuera)


async def test_una_actividad_no_se_guarda_en_un_poa_de_area_que_no_existe(tablero):
    with pytest.raises(ResourceNotFoundError):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=INEXISTENTE, name="Sin POA")
        )


@pytest.mark.parametrize(
    "nivel",
    [
        NodeKind.EJE,
        NodeKind.OBJETIVO_GENERAL,
        NodeKind.OBJETIVO_ESPECIFICO,
        NodeKind.LINEA_ESTRATEGICA,
    ],
    ids=lambda nivel: nivel.value,
)
async def test_una_actividad_no_cuelga_de_ninguno_de_los_cuatro_niveles_sobre_la_accion(
    tablero, nivel
):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="accion"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                name="Mal alineada",
                node_id=await _nodo_raiz(tablero, nivel),
            )
        )

    assert await tablero.repo.list_activities(poa_area.id) == []


async def test_una_actividad_cuelga_de_un_nodo_de_nivel_accion(tablero):
    poa_area = await _poa_area(tablero)
    accion = await _nodo_raiz(tablero, NodeKind.ACCION)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Bien alineada", node_id=accion)
    )

    assert (await tablero.repo.get_activity(guardada.id)).node_id == accion


async def test_una_actividad_no_cuelga_de_un_nodo_que_no_existe(tablero):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="no existe"):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name="Sin nodo", node_id=INEXISTENTE)
        )


async def test_a_un_nodo_retirado_no_se_le_cuelgan_actividades_nuevas(tablero):
    poa_area = await _poa_area(tablero)
    retirado = await _nodo_raiz(tablero, NodeKind.ACCION, activo=False)

    with pytest.raises(ValidationError, match="retirado"):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name="Nueva", node_id=retirado)
        )


async def test_una_actividad_existente_tampoco_se_muda_a_un_nodo_retirado(tablero):
    poa_area = await _poa_area(tablero)
    guardada = await _actividad_completa(tablero, poa_area)
    retirado = await _nodo_raiz(tablero, NodeKind.ACCION, activo=False)

    with pytest.raises(ValidationError, match="retirado"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                activity_id=guardada.id,
                version=guardada.version,
                node_id=retirado,
            )
        )

    assert (await tablero.repo.get_activity(guardada.id)).node_id == guardada.node_id


async def test_una_actividad_puede_colgar_de_un_nodo_desactivado_ya_usado(tablero):
    poa_area = await _poa_area(tablero)
    accion = await _nodo_raiz(tablero, NodeKind.ACCION)
    guardada = await _actividad_completa(tablero, poa_area, nodo_id=accion)

    await tablero.arbol.deactivate(accion)

    sigue_ahi = await tablero.repo.get_activity(guardada.id)
    assert sigue_ahi.node_id == accion
    assert [una.id for una in await tablero.repo.list_activities(poa_area.id)] == [guardada.id]

    reeditada = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=guardada.id,
            version=sigue_ahi.version,
            name="Con otro nombre y el mismo nodo retirado",
        )
    )

    assert reeditada.node_id == accion
    assert (await tablero.repo.get_activity(guardada.id)).node_id == accion
    assert (await tablero.arbol.get_by_id(accion)).is_active is False


async def test_se_presenta_aunque_la_accion_del_pide_se_haya_retirado(tablero):
    poa_area = await _poa_area(tablero)
    accion = await _nodo_raiz(tablero, NodeKind.ACCION)
    await _actividad_completa(tablero, poa_area, nodo_id=accion)
    await tablero.arbol.deactivate(accion)

    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    assert enviado.status is PoaAreaStatus.ENVIADO


@pytest.mark.parametrize(
    "meses",
    [
        [MonthlyTarget(month=mes, target=Decimal(1)) for mes in range(1, 12)],
        [MonthlyTarget(month=mes, target=Decimal(1)) for mes in range(1, 14)],
        [MonthlyTarget(month=1, target=Decimal(1))],
        [MonthlyTarget(month=3, target=Decimal(1)) for _ in range(12)],
        [MonthlyTarget(month=mes, target=Decimal(1)) for mes in range(0, 12)],
        [MonthlyTarget(month=mes, target=Decimal(1)) for mes in (*MESES_DEL_EJERCICIO, 1)],
    ],
    ids=[
        "once",
        "trece",
        "uno",
        "el_mismo_doce_veces",
        "del_cero_al_once",
        "los_doce_mas_uno_repetido",
    ],
)
async def test_la_programacion_de_una_actividad_son_los_doce_meses_una_sola_vez(tablero, meses):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="doce meses"):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name="Mal programada", monthly=meses)
        )

    assert await tablero.repo.list_activities(poa_area.id) == []


async def test_sacar_un_mes_de_la_programacion_sin_limpiar_su_meta_no_se_guarda(tablero):
    poa_area = await _poa_area(tablero)
    meses = _programacion(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)
    meses[6] = MonthlyTarget(month=7, target=Decimal(4), included=False)

    with pytest.raises(ValidationError, match="cero en el mismo guardado"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id, name="Con el número sin limpiar", monthly=meses
            )
        )

    assert await tablero.repo.list_activities(poa_area.id) == []


def test_la_suma_anual_mira_la_bandera_y_no_solo_el_cero():
    actividad = Activity(
        poa_area_id=1,
        name="Con un mes fuera de la programación y con número",
        monthly=[
            MonthlyTarget(month=mes, target=Decimal(2), included=mes != 7)
            for mes in MESES_DEL_EJERCICIO
        ],
    )

    assert actividad.included_sum() == Decimal(22)
    with pytest.raises(ValidationError, match="cero en el mismo guardado"):
        actividad.validate()


async def test_un_mes_incluido_en_cero_se_distingue_de_un_mes_fuera_de_la_programacion(tablero):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name="Con un mes en cero y otro fuera de la programación",
            monthly=_programacion(DOCE_METAS_DESIGUALES_QUE_SUMAN_24, sin_incluir=(8,)),
        )
    )

    leidos = (await tablero.repo.get_activity(guardada.id)).months()
    assert (leidos[2].target, leidos[2].included) == (0, True)
    assert (leidos[7].target, leidos[7].included) == (0, False)


@pytest.mark.parametrize(
    "meta", [Decimal("-0.0001"), Decimal("-1")], ids=["casi_cero", "menos_uno"]
)
async def test_una_meta_negativa_no_se_guarda_pero_cero_si(tablero, meta):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="negativa"):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name="Negativa", annual_target=meta)
        )

    en_cero = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="En cero", annual_target=Decimal(0))
    )
    assert (await tablero.repo.get_activity(en_cero.id)).annual_target == 0


@pytest.mark.parametrize(
    "meta",
    [Decimal("0.00001"), Decimal("1.23456"), Decimal(10) ** 14, Decimal("NaN")],
    ids=["un_decimal_de_mas", "cinco_decimales", "un_entero_de_mas", "no_es_un_numero"],
)
async def test_una_meta_que_la_base_no_guarda_tal_cual_se_rechaza_en_vez_de_redondearse(
    tablero, meta
):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError):
        await tablero.guardar().execute(
            SaveActivityCommand(poa_area_id=poa_area.id, name="Fuera de rango", annual_target=meta)
        )

    assert await tablero.repo.list_activities(poa_area.id) == []


async def test_la_meta_mas_alta_que_la_columna_guarda_se_acepta(tablero):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name="Con el tope exacto de la columna",
            annual_target=META_MAS_ALTA_QUE_CABE,
        )
    )

    assert (await tablero.repo.get_activity(guardada.id)).annual_target == META_MAS_ALTA_QUE_CABE


async def test_una_meta_mensual_que_la_base_redondearia_se_rechaza(tablero):
    poa_area = await _poa_area(tablero)
    meses = _programacion(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)
    meses[4] = MonthlyTarget(month=5, target=Decimal("5.00001"))

    with pytest.raises(ValidationError, match="mes 5"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id, name="Con un mes que no cabe", monthly=meses
            )
        )


async def test_una_meta_con_cuatro_decimales_se_guarda_y_se_lee_igual(tablero):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id, name="Con decimales", annual_target=Decimal("1.2345")
        )
    )

    assert (await tablero.repo.get_activity(guardada.id)).annual_target == Decimal("1.2345")


async def test_guardar_con_una_version_vieja_no_pisa_el_cambio_ajeno(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area, nombre="Como la abrió el área")

    otra_persona = await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=actividad.id,
            version=1,
            name="Como la dejó la otra persona",
        )
    )
    assert otra_persona.version == 2

    with pytest.raises(ConflictError, match="otra solicitud"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                activity_id=actividad.id,
                version=1,
                name="Lo que llegó tarde",
            )
        )

    guardada = await tablero.repo.get_activity(actividad.id)
    assert (guardada.name, guardada.version) == ("Como la dejó la otra persona", 2)


async def test_guardar_con_la_version_que_la_fila_trae_si_guarda_y_sube_el_contador(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area)

    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id, activity_id=actividad.id, version=1, name="Segunda mano"
        )
    )
    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id, activity_id=actividad.id, version=2, name="Tercera mano"
        )
    )

    guardada = await tablero.repo.get_activity(actividad.id)
    assert (guardada.name, guardada.version) == ("Tercera mano", 3)


async def test_editar_una_actividad_sin_decir_sobre_que_version_no_se_guarda(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area, nombre="La original")

    with pytest.raises(ValidationError, match="versión"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id, activity_id=actividad.id, name="Sin versión"
            )
        )

    assert (await tablero.repo.get_activity(actividad.id)).name == "La original"


async def test_lo_que_el_guardado_parcial_no_manda_no_se_borra(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area)

    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=actividad.id,
            version=actividad.version,
            name="Sólo le cambié el nombre",
        )
    )

    guardada = await tablero.repo.get_activity(actividad.id)
    assert guardada.name == "Sólo le cambié el nombre"
    assert guardada.node_id == actividad.node_id
    assert guardada.unit_id == actividad.unit_id
    assert guardada.evaluation_method == actividad.evaluation_method
    assert guardada.annual_target == actividad.annual_target
    assert [mes.target for mes in guardada.months()] == list(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)


async def test_editar_una_actividad_con_una_programacion_invalida_no_la_guarda(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area, nombre="La original")
    meses = _programacion(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)
    meses[6] = MonthlyTarget(month=7, target=Decimal(4), included=False)

    with pytest.raises(ValidationError, match="cero en el mismo guardado"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                activity_id=actividad.id,
                version=actividad.version,
                name="Con el número sin limpiar",
                monthly=meses,
            )
        )

    guardada = await tablero.repo.get_activity(actividad.id)
    assert (guardada.name, guardada.version) == ("La original", 1)
    assert [mes.target for mes in guardada.months()] == list(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)


async def test_tocar_la_actividad_que_el_repositorio_entrego_no_cambia_lo_guardado(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area, nombre="Como quedó guardada")

    entregada = await tablero.repo.get_activity(actividad.id)
    entregada.name = "Tocada por fuera"
    entregada.annual_target = Decimal(999)
    entregada.monthly[0].target = Decimal(99)
    entregada.monthly.pop()

    guardada = await tablero.repo.get_activity(actividad.id)
    assert guardada.name == "Como quedó guardada"
    assert guardada.annual_target == Decimal(24)
    assert [mes.target for mes in guardada.months()] == list(DOCE_METAS_DESIGUALES_QUE_SUMAN_24)


async def test_una_actividad_nueva_nace_en_la_version_uno_aunque_llegue_con_otra(tablero):
    poa_area = await _poa_area(tablero)
    actividad = Activity(poa_area_id=poa_area.id, name="Llega con la siete", version=7)

    await tablero.repo.add_activity(actividad)

    assert (await tablero.repo.get_activity(actividad.id)).version == 1


async def test_una_actividad_que_nace_retirada_se_guarda_retirada(tablero):
    poa_area = await _poa_area(tablero)

    guardada = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Nace retirada", is_active=False)
    )

    assert (await tablero.repo.get_activity(guardada.id)).is_active is False
    assert await tablero.repo.list_activities(poa_area.id) == []


async def test_el_listado_sigue_el_orden_del_alta_y_no_el_del_ultimo_guardado(tablero):
    poa_area = await _poa_area(tablero)
    primera = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Zapatear el patio")
    )
    segunda = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Mejorar el taller")
    )
    tercera = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="Archivar lo viejo")
    )

    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=primera.id,
            version=primera.version,
            name="Zapatear el patio, corregido",
        )
    )

    assert [una.id for una in await tablero.repo.list_activities(poa_area.id)] == [
        primera.id,
        segunda.id,
        tercera.id,
    ]


async def test_una_actividad_de_otro_poa_de_area_no_se_edita_desde_este(tablero):
    poa_area = await _poa_area(tablero)
    ajeno = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, ajeno, nombre="Del área vecina")

    with pytest.raises(ResourceNotFoundError):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                activity_id=actividad.id,
                version=actividad.version,
                name="Robada",
            )
        )

    assert (await tablero.repo.get_activity(actividad.id)).name == "Del área vecina"


async def test_no_se_presenta_si_los_meses_no_suman_la_meta(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area, metas=DOCE_METAS_DESIGUALES_QUE_SUMAN_22)

    with pytest.raises(ValidationError, match="suman 22 de 24"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    assert (await tablero.repo.get_poa_area(poa_area.id)).status is PoaAreaStatus.BORRADOR


async def test_no_se_presenta_si_los_meses_suman_mas_que_la_meta(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area, metas=DOCE_METAS_DESIGUALES_QUE_SUMAN_30)

    with pytest.raises(ValidationError, match="suman 30 de 24"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    assert (await tablero.repo.get_poa_area(poa_area.id)).status is PoaAreaStatus.BORRADOR


async def test_los_meses_no_incluidos_no_cuentan_en_la_suma(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(
        tablero,
        poa_area,
        meta_anual=Decimal(24),
        metas=ONCE_METAS_DESIGUALES_QUE_SUMAN_24_Y_UN_DOCEAVO_EN_CERO,
        sin_incluir=(12,),
    )

    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    assert enviado.status is PoaAreaStatus.ENVIADO


async def test_un_mes_no_incluido_no_tapa_el_hueco_que_dejan_los_once_incluidos(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(
        tablero,
        poa_area,
        meta_anual=Decimal(24),
        metas=ONCE_METAS_DESIGUALES_QUE_SUMAN_22_Y_UN_DOCEAVO_EN_CERO,
        sin_incluir=(12,),
    )

    with pytest.raises(ValidationError, match="suman 22 de 24"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )


async def test_se_presenta_cuando_cada_actividad_activa_esta_completa(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area, nombre="La primera")
    await _actividad_completa(tablero, poa_area, nombre="La segunda")

    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    assert (enviado.status, enviado.version) == (PoaAreaStatus.ENVIADO, 2)
    guardado = await tablero.repo.get_poa_area(poa_area.id)
    assert (guardado.status, guardado.version) == (PoaAreaStatus.ENVIADO, 2)


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        ("node_id", "la acción del PIDE"),
        ("unit_id", "la unidad de medida"),
        ("evaluation_method", "el método de evaluación"),
        ("annual_target", "la meta anual"),
    ],
)
async def test_presentar_exige_los_cuatro_campos_que_el_borrador_deja_vacios(
    tablero, campo, esperado
):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area, nombre="Casi completa")
    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=actividad.id,
            version=actividad.version,
            **{campo: None},
        )
    )

    with pytest.raises(ValidationError, match=esperado):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    assert (await tablero.repo.get_poa_area(poa_area.id)).status is PoaAreaStatus.BORRADOR


async def test_presentar_exige_los_doce_meses_de_cada_actividad(tablero):
    poa_area = await _poa_area(tablero)
    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name="Sin programar nada",
            node_id=await _nodo_raiz(tablero),
            unit_id=await tablero.nueva_unidad(),
            evaluation_method="Listas de asistencia",
            annual_target=Decimal(24),
        )
    )

    with pytest.raises(ValidationError, match="doce meses"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )


async def test_la_negativa_dice_que_actividad_y_que_le_falta(tablero):
    poa_area = await _poa_area(tablero)
    incompleta = await _actividad_completa(tablero, poa_area, nombre="Sin unidad ni método")
    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=incompleta.id,
            version=incompleta.version,
            unit_id=None,
            evaluation_method=None,
        )
    )
    await _actividad_completa(
        tablero,
        poa_area,
        nombre="Con la suma descuadrada",
        metas=DOCE_METAS_DESIGUALES_QUE_SUMAN_22,
    )
    await _actividad_completa(tablero, poa_area, nombre="La que sí está completa")

    with pytest.raises(ValidationError) as caido:
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    dicho = str(caido.value)
    assert "2 actividades están incompletas" in dicho
    assert "«Sin unidad ni método» le falta la unidad de medida y el método de" in dicho
    assert "A «Con la suma descuadrada» le falta que sus meses incluidos" in dicho
    assert "suman 22 de 24" in dicho
    assert "La que sí está completa" not in dicho


async def test_una_actividad_retirada_no_estorba_al_presentar(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area, nombre="La que vale")
    retirada = await tablero.guardar().execute(
        SaveActivityCommand(poa_area_id=poa_area.id, name="La que se retiró a medias")
    )
    await tablero.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=retirada.id,
            version=retirada.version,
            is_active=False,
        )
    )

    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    assert enviado.status is PoaAreaStatus.ENVIADO
    assert retirada.id not in [una.id for una in await tablero.repo.list_activities(poa_area.id)]
    assert retirada.id in [
        una.id for una in await tablero.repo.list_activities(poa_area.id, include_inactive=True)
    ]


async def test_un_poa_de_area_sin_actividades_activas_no_se_presenta(tablero):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ValidationError, match="ninguna actividad activa"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )


async def test_un_poa_de_area_sin_responsable_no_se_presenta(tablero):
    poa_area = await _poa_area(tablero, con_responsable=False)
    await _actividad_completa(tablero, poa_area)

    with pytest.raises(ValidationError, match="no tiene responsable asignado"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    assert (await tablero.repo.get_poa_area(poa_area.id)).status is PoaAreaStatus.BORRADOR


async def test_un_poa_de_area_sin_responsable_si_se_captura(tablero):
    poa_area = await _poa_area(tablero, con_responsable=False)

    guardada = await _actividad_completa(tablero, poa_area, nombre="Capturada sin responsable")

    assert (await tablero.repo.get_activity(guardada.id)).name == "Capturada sin responsable"


async def test_la_negativa_junta_la_falta_de_responsable_con_las_actividades_incompletas(tablero):
    poa_area = await _poa_area(tablero, con_responsable=False)
    await _actividad_completa(
        tablero,
        poa_area,
        nombre="Con la suma descuadrada",
        metas=DOCE_METAS_DESIGUALES_QUE_SUMAN_22,
    )

    with pytest.raises(ValidationError) as caido:
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    dicho = str(caido.value)
    assert "no tiene responsable asignado" in dicho
    assert "1 actividad está incompleta" in dicho
    assert "suman 22 de 24" in dicho


async def test_dar_el_responsable_al_area_deja_presentar_lo_que_antes_no_se_podia(tablero):
    poa_area = await _poa_area(tablero, con_responsable=False)
    await _actividad_completa(tablero, poa_area)
    with pytest.raises(ValidationError, match="no tiene responsable asignado"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )

    await tablero.dar_responsable(poa_area.area_id)

    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )
    assert enviado.status is PoaAreaStatus.ENVIADO


async def test_un_area_con_usuarios_pero_ninguno_con_el_rol_no_tiene_responsable(tablero):
    area = await tablero.nueva_area()
    await tablero.nuevo_usuario(area, Role.CAPTURISTA_POA.value)
    await tablero.nuevo_usuario(area, Role.REVISOR_POA.value)
    await tablero.nuevo_usuario(area, None)

    assert await tablero.liderazgo.has_person_in_charge(area) is False


async def test_un_area_vacia_tampoco_tiene_responsable(tablero):
    area = await tablero.nueva_area()

    assert await tablero.liderazgo.has_person_in_charge(area) is False


async def test_un_area_con_el_rol_de_responsable_lo_tiene(tablero):
    area = await tablero.nueva_area()
    await tablero.nuevo_usuario(area, Role.CAPTURISTA_POA.value)
    await tablero.nuevo_usuario(area, Role.RESPONSABLE_AREA.value)

    assert await tablero.liderazgo.has_person_in_charge(area) is True


async def test_un_responsable_desactivado_no_responde_por_el_area(tablero):
    area = await tablero.nueva_area()
    await tablero.nuevo_usuario(area, Role.RESPONSABLE_AREA.value, activo=False)

    assert await tablero.liderazgo.has_person_in_charge(area) is False


async def test_el_responsable_de_otra_area_no_responde_por_esta(tablero):
    area = await tablero.nueva_area()
    otra = await tablero.nueva_area()
    await tablero.nuevo_usuario(area, Role.CAPTURISTA_POA.value)
    await tablero.nuevo_usuario(otra, Role.RESPONSABLE_AREA.value)

    assert await tablero.liderazgo.has_person_in_charge(area) is False
    assert await tablero.liderazgo.has_person_in_charge(otra) is True


AREA_CON_RESPONSABLE = 7
AREA_SIN_NADIE = 8


async def test_en_memoria_el_liderazgo_lee_los_usuarios_de_la_aplicacion():
    aplicacion = create_app(
        Settings(
            environment="testing",
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
        )
    )
    try:
        await CreateUser(
            aplicacion.state.user_repository,
            aplicacion.state.password_hasher,
            aplicacion.state.event_bus,
        ).execute(
            RegisterUserCommand(
                email=f"responsable-{uuid4().hex}@upchiapas.edu.mx",
                full_name="Responsable del área",
                password="password-seguro",
                roles={Role.RESPONSABLE_AREA},
                area_id=AREA_CON_RESPONSABLE,
            )
        )
        liderazgo = aplicacion.state.area_leadership

        assert await liderazgo.has_person_in_charge(AREA_CON_RESPONSABLE) is True
        assert await liderazgo.has_person_in_charge(AREA_SIN_NADIE) is False
    finally:
        await aplicacion.state.notification_service.close()


async def test_un_poa_de_area_ya_enviado_no_se_vuelve_a_enviar_ni_admite_cambios(tablero):
    poa_area = await _poa_area(tablero)
    actividad = await _actividad_completa(tablero, poa_area)
    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    with pytest.raises(InvalidStateError, match="ya fue enviado"):
        await tablero.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=enviado.version)
        )
    with pytest.raises(InvalidStateError, match="ya fue enviado"):
        await tablero.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id,
                activity_id=actividad.id,
                version=actividad.version,
                name="Después de enviar",
            )
        )

    guardado = await tablero.repo.get_poa_area(poa_area.id)
    assert (guardado.status, guardado.version) == (PoaAreaStatus.ENVIADO, 2)
    assert (await tablero.repo.get_activity(actividad.id)).name == actividad.name


async def test_abrir_un_poa_de_area_ya_enviado_lo_devuelve_enviado(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area)
    enviado = await tablero.enviar().execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
    )

    reabierto = await tablero.abrir().execute(
        OpenPoaAreaCommand(exercise_id=poa_area.exercise_id, area_id=poa_area.area_id)
    )

    assert (reabierto.id, reabierto.status, reabierto.version) == (
        poa_area.id,
        PoaAreaStatus.ENVIADO,
        enviado.version,
    )


async def test_presentar_con_una_version_vieja_no_pisa_el_cambio_ajeno(tablero):
    poa_area = await _poa_area(tablero)
    await _actividad_completa(tablero, poa_area)
    await tablero.repo.save_poa_area_if_version_matches(
        replace(poa_area, status=PoaAreaStatus.BORRADOR, version=1)
    )

    with pytest.raises(ConflictError, match="otra solicitud"):
        await tablero.enviar().execute(SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=1))

    guardado = await tablero.repo.get_poa_area(poa_area.id)
    assert (guardado.status, guardado.version) == (PoaAreaStatus.BORRADOR, 2)


async def test_un_poa_de_area_que_no_existe_no_se_presenta(tablero):
    with pytest.raises(ResourceNotFoundError):
        await tablero.enviar().execute(SubmitPoaAreaCommand(poa_area_id=INEXISTENTE, version=1))


async def test_un_area_tiene_un_solo_poa_por_ejercicio(tablero):
    poa_area = await _poa_area(tablero)

    with pytest.raises(ConflictError, match="ya tiene su POA"):
        await tablero.repo.add_poa_area(
            PoaArea(exercise_id=poa_area.exercise_id, area_id=poa_area.area_id)
        )


async def test_una_unidad_de_medida_que_no_existe_no_se_guarda(tablero_postgresql):
    poa_area = await _poa_area(tablero_postgresql)

    with pytest.raises(ValidationError, match="unidad de medida no existe"):
        await tablero_postgresql.guardar().execute(
            SaveActivityCommand(
                poa_area_id=poa_area.id, name="Con unidad inventada", unit_id=INEXISTENTE
            )
        )


async def test_una_actividad_escrita_sobre_un_poa_de_area_que_no_existe_no_entra(tablero):
    with pytest.raises(ResourceNotFoundError, match="POA del área no existe"):
        await tablero.repo.add_activity(
            Activity(poa_area_id=INEXISTENTE, name="Sobre un POA inventado")
        )


async def test_una_actividad_escrita_sobre_un_nodo_que_no_existe_no_entra(tablero_postgresql):
    poa_area = await _poa_area(tablero_postgresql)

    with pytest.raises(ValidationError, match="acción del PIDE a la que responde"):
        await tablero_postgresql.repo.add_activity(
            Activity(poa_area_id=poa_area.id, name="Sobre un nodo inventado", node_id=INEXISTENTE)
        )

    assert await tablero_postgresql.repo.list_activities(poa_area.id) == []


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [("exercise_id", "ejercicio POA no existe"), ("area_id", "área no existe")],
)
async def test_un_poa_de_area_de_un_ejercicio_o_un_area_que_no_existen_no_se_guarda(
    tablero_postgresql, campo, esperado
):
    valores = {
        "exercise_id": await tablero_postgresql.nuevo_ejercicio(),
        "area_id": await tablero_postgresql.nueva_area(),
        campo: INEXISTENTE,
    }

    with pytest.raises(ValidationError, match=esperado):
        await tablero_postgresql.repo.add_poa_area(PoaArea(**valores))


async def test_una_programacion_incompleta_escrita_por_fuera_frena_el_envio(
    tablero_postgresql,
):
    poa_area = await _poa_area(tablero_postgresql)
    actividad = await _actividad_completa(tablero_postgresql, poa_area)
    await tablero_postgresql.conexion.execute(
        text("DELETE FROM poa_inst_programacion_mensual WHERE actividad_id = :id AND mes = 4"),
        {"id": actividad.id},
    )

    with pytest.raises(ValidationError, match="doce meses"):
        await tablero_postgresql.enviar().execute(
            SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=poa_area.version)
        )


async def test_la_programacion_guardada_reemplaza_la_anterior_y_no_se_suma_a_ella(
    tablero_postgresql,
):
    poa_area = await _poa_area(tablero_postgresql)
    actividad = await _actividad_completa(tablero_postgresql, poa_area)

    await tablero_postgresql.guardar().execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=actividad.id,
            version=actividad.version,
            monthly=_programacion(DOCE_METAS_DESIGUALES_QUE_SUMAN_22),
        )
    )

    cuantas = (
        await tablero_postgresql.conexion.execute(
            text("SELECT count(*) FROM poa_inst_programacion_mensual WHERE actividad_id = :id"),
            {"id": actividad.id},
        )
    ).scalar_one()
    assert cuantas == 12
    leidos = (await tablero_postgresql.repo.get_activity(actividad.id)).months()
    assert [mes.target for mes in leidos] == list(DOCE_METAS_DESIGUALES_QUE_SUMAN_22)
