from __future__ import annotations

import asyncio
import json
import os
import sys
import unicodedata
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine
from tests.test_instalacion_nueva import (
    _consultar,
    _migrar,
    base_recien_nacida,  # noqa: F401
)

from app.modules.institutional_catalogs.domain.entities import InstrumentVersion
from app.modules.institutional_catalogs.domain.ports.repositories import (
    InstrumentRepository,
    InstrumentVersionRepository,
)
from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.institutional_catalogs.domain.strategic_tree_entities import NodeKind
from app.modules.institutional_catalogs.infrastructure.repository import (
    InMemoryInstrumentRepository,
    InMemoryInstrumentVersionRepository,
)
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyInstrumentRepository,
    SqlAlchemyInstrumentVersionRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_repository import (
    InMemoryStrategicTreeRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)
from app.scripts.cargar_pide import (
    CARGA_SIN_CONFIRMAR,
    SEMILLA_DEL_PIDE,
    ResumenCarga,
    asegurar_version,
    cargar_pide,
    es_la_misma_base,
    leer_semilla,
    main,
    url_de_la_base_del_entorno,
)
from app.shared.domain.captured_text import INVISIBLES_QUE_SOBREVIVEN_AL_RECORTE
from app.shared.domain.exceptions import ConflictError, ValidationError

EJE = NodeKind.EJE
OBJETIVO_GENERAL = NodeKind.OBJETIVO_GENERAL
OBJETIVO_ESPECIFICO = NodeKind.OBJETIVO_ESPECIFICO
LINEA = NodeKind.LINEA_ESTRATEGICA
ACCION = NodeKind.ACCION

NODOS_QUE_IMPRIME_EL_DOCUMENTO = {
    EJE: 5,
    OBJETIVO_GENERAL: 5,
    OBJETIVO_ESPECIFICO: 25,
    LINEA: 24,
    ACCION: 107,
}
TOTAL_QUE_IMPRIME_EL_DOCUMENTO = sum(NODOS_QUE_IMPRIME_EL_DOCUMENTO.values())

PADRE_DE_CADA_NIVEL = {
    EJE: None,
    OBJETIVO_GENERAL: EJE,
    OBJETIVO_ESPECIFICO: OBJETIVO_GENERAL,
    LINEA: OBJETIVO_ESPECIFICO,
    ACCION: LINEA,
}

EJE_1_DEL_DOCUMENTO = (
    "Garantizar la Formación Integral que Desarrolle las Capacidades del Estudiante."
)
OBJETIVO_GENERAL_1_DEL_DOCUMENTO = (
    "Consolidar un proceso formativo innovador y de excelencia, que garantice el desarrollo de "
    "competencias profesionales y ciudadanas de alto nivel en los estudiantes, asegurando su "
    "egreso como profesionales competitivos, éticos y con capacidad de aprendizaje a lo largo "
    "de la vida, listos para contribuir al desarrollo sostenible de la sociedad."
)
OBJETIVO_ESPECIFICO_111_DEL_DOCUMENTO = (
    "Fortalecer el Programa Institucional de Tutorías y el Seguimiento de Egresados."
)

ANCESTROS_QUE_IMPRIME_EL_DOCUMENTO = {
    "1.1.1.1.4": [
        ("1", EJE, EJE_1_DEL_DOCUMENTO),
        ("1.1", OBJETIVO_GENERAL, OBJETIVO_GENERAL_1_DEL_DOCUMENTO),
        ("1.1.1", OBJETIVO_ESPECIFICO, OBJETIVO_ESPECIFICO_111_DEL_DOCUMENTO),
        (
            "1.1.1.1",
            LINEA,
            "Acompañamiento académico y vinculación para el fortalecimiento de trayectorias "
            "formativas.",
        ),
    ],
    "1.1.1.3.2": [
        ("1", EJE, EJE_1_DEL_DOCUMENTO),
        ("1.1", OBJETIVO_GENERAL, OBJETIVO_GENERAL_1_DEL_DOCUMENTO),
        ("1.1.1", OBJETIVO_ESPECIFICO, OBJETIVO_ESPECIFICO_111_DEL_DOCUMENTO),
        ("1.1.1.3", LINEA, "Apoyo para la Innovación extracurricular."),
    ],
}

INDICADORES_QUE_IMPRIME_EL_DOCUMENTO = {
    "1.1.1.1.1": (
        "Actualizar el Programa Institucional de Tutorías.",
        "Programa de Tutoría Actualizado / Programa de Tutoría x 100",
    ),
    "1.1.1.2.3": (
        "Proporcionar servicios complementarios (Cafetería, papelería).",
        "índice de satisfacción (%) = ∑puntaje obtenido / N° puntaje máximo ×100",
    ),
    "3.1.1.2.5": (
        "Realizar estudios de pertinencia para nueva oferta educativa.",
        "Número de estudios de pertinencia concluidos para nuevas propuestas de programas "
        "educativos en el año",
    ),
    "5.1.1.3.2": (
        "Gestionar recursos adicionales para la operación institucional.",
        "Suma de los recursos adicionales ejercidos en el periodo",
    ),
}

SEMILLA_CON_PUNTOS_ALTERNADOS = {
    "instrumento": {"codigo": "PUNTOS", "nombre": "Instrumento de los puntos"},
    "version": {"etiqueta": "V1", "vigente_desde": "2025-01-01", "origen": "Una prueba"},
    "nodos": [
        {"clave": "9.", "nivel": "eje", "padre": None, "denominacion": "Eje con punto"},
        {
            "clave": "9.1",
            "nivel": "objetivo_general",
            "padre": "9",
            "denominacion": "Objetivo general sin punto",
        },
        {
            "clave": "9.1.1.",
            "nivel": "objetivo_especifico",
            "padre": "9.1",
            "denominacion": "Objetivo específico con punto",
        },
        {
            "clave": "9.1.1.1",
            "nivel": "linea_estrategica",
            "padre": "9.1.1",
            "denominacion": "Línea sin punto",
        },
        {
            "clave": "9.1.1.1.1.",
            "nivel": "accion",
            "padre": "9.1.1.1",
            "denominacion": "Acción con punto",
            "formula_indicador": "A / B x 100",
        },
    ],
}

CLAVES_SIN_EL_PUNTO_FINAL = ["9", "9.1", "9.1.1", "9.1.1.1", "9.1.1.1.1"]

SEMILLA_CON_INVISIBLES = {
    "instrumento": {"codigo": "INVISIBLES", "nombre": "Instrumento de los invisibles"},
    "version": {"etiqueta": "V1", "vigente_desde": "2025-01-01", "origen": "Una prueba"},
    "nodos": [
        {
            "clave": "8.\u200b",
            "nivel": "eje",
            "padre": None,
            "denominacion": "Eje\ufeff con invisibles",
        },
        {
            "clave": "8.\u00ad1",
            "nivel": "accion",
            "padre": "8",
            "denominacion": "\u200bAccion con invisibles",
            "formula_indicador": "A\u200b / B\u00ad x 100",
        },
    ],
}

SEMILLA_CON_UN_PADRE_QUE_NO_ESTA = {
    "instrumento": {"codigo": "HUERFANO", "nombre": "Instrumento del huerfano"},
    "version": {"etiqueta": "V1", "vigente_desde": "2025-01-01"},
    "nodos": [
        {"clave": "8.", "nivel": "eje", "padre": None, "denominacion": "Eje"},
        {
            "clave": "8.1.1",
            "nivel": "objetivo_especifico",
            "padre": "8.1",
            "denominacion": "Cuelga de un objetivo general que la semilla no trae",
        },
    ],
}

INSTRUMENTO_QUE_NADIE_CREO = 10**9

CONTEOS_DE_LA_CARGA = (
    "SELECT (SELECT count(*) FROM instrumentos)           AS instrumentos,"
    "       (SELECT count(*) FROM instrumento_versiones)  AS versiones,"
    "       (SELECT count(*) FROM nodos_estrategicos)     AS nodos,"
    "       (SELECT count(formula_indicador) FROM nodos_estrategicos) AS con_formula"
)


@dataclass
class Carga:
    instrumentos: InstrumentRepository
    versiones: InstrumentVersionRepository
    arbol: StrategicTreeRepository
    conexion: AsyncConnection | None = None


def _en_memoria() -> Carga:
    return Carga(
        instrumentos=InMemoryInstrumentRepository(),
        versiones=InMemoryInstrumentVersionRepository(),
        arbol=InMemoryStrategicTreeRepository(),
    )


@asynccontextmanager
async def _en_postgresql():
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
            try:
                yield Carga(
                    instrumentos=SqlAlchemyInstrumentRepository(fabrica),
                    versiones=SqlAlchemyInstrumentVersionRepository(fabrica),
                    arbol=SqlAlchemyStrategicTreeRepository(fabrica),
                    conexion=conexion,
                )
            finally:
                await transaccion.rollback()
    finally:
        await motor.dispose()


@pytest.fixture(params=["memoria", "postgresql"])
async def carga(request):
    if request.param == "memoria":
        yield _en_memoria()
    else:
        async with _en_postgresql() as en_postgresql:
            yield en_postgresql


@pytest.fixture
async def carga_postgresql():
    async with _en_postgresql() as en_postgresql:
        yield en_postgresql


def _escribir(tmp_path: Path, semilla: dict) -> Path:
    copia = json.loads(json.dumps(semilla))
    copia["instrumento"]["codigo"] = f"T{uuid4().hex[:8].upper()}"
    copia["instrumento"]["nombre"] = f"{copia['instrumento']['nombre']} {uuid4().hex[:8]}"
    ruta = tmp_path / f"semilla-{uuid4().hex[:8]}.json"
    ruta.write_text(json.dumps(copia, ensure_ascii=False), encoding="utf-8")
    return ruta


@pytest.fixture
def ruta_del_pide(tmp_path) -> Path:
    return _escribir(tmp_path, leer_semilla(SEMILLA_DEL_PIDE))


async def _version_de(carga: Carga, ruta: Path) -> int:
    return await asegurar_version(ruta, carga.instrumentos, carga.versiones)


async def _cargar(carga: Carga, ruta: Path):
    version_id = await _version_de(carga, ruta)
    return version_id, await cargar_pide(ruta, version_id, carga.arbol)


async def _instrumento_de(carga: Carga, ruta: Path):
    codigo = leer_semilla(ruta)["instrumento"]["codigo"]
    return next(
        instrumento
        for instrumento in await carga.instrumentos.list(active_only=False)
        if instrumento.code == codigo
    )


def test_la_semilla_trae_el_capitulo_entero_del_documento():
    nodos = leer_semilla(SEMILLA_DEL_PIDE)["nodos"]

    assert Counter(nodo["nivel"] for nodo in nodos) == {
        nivel.value: cuantos for nivel, cuantos in NODOS_QUE_IMPRIME_EL_DOCUMENTO.items()
    }
    con_formula = [nodo for nodo in nodos if nodo.get("formula_indicador")]
    assert len(con_formula) == NODOS_QUE_IMPRIME_EL_DOCUMENTO[ACCION]
    assert {nodo["nivel"] for nodo in con_formula} == {ACCION.value}


def test_la_semilla_no_trae_caracteres_invisibles():
    semilla = SEMILLA_DEL_PIDE.read_text(encoding="utf-8")

    invisibles = {
        caracter
        for caracter in semilla
        if caracter not in " \n"
        and (unicodedata.category(caracter) in {"Cc", "Cf", "Co", "Cs"} or caracter.isspace())
    }

    assert invisibles == set()


def test_el_codigo_tampoco_trae_los_invisibles_que_el_dominio_quita():
    raiz = SEMILLA_DEL_PIDE.parents[2]

    con_invisibles = [
        str(ruta.relative_to(raiz))
        for carpeta in ("app", "tests")
        for ruta in sorted((raiz / carpeta).rglob("*.py"))
        if any(
            invisible in ruta.read_text(encoding="utf-8")
            for invisible in INVISIBLES_QUE_SOBREVIVEN_AL_RECORTE
        )
    ]

    assert con_invisibles == []


def test_cada_clave_de_la_semilla_es_unica_sin_su_punto_final():
    claves = [nodo["clave"].rstrip(".") for nodo in leer_semilla(SEMILLA_DEL_PIDE)["nodos"]]

    repetidas = [clave for clave, cuantas in Counter(claves).items() if cuantas > 1]

    assert repetidas == []


async def test_la_carga_es_idempotente(carga, ruta_del_pide):
    version_id, primera = await _cargar(carga, ruta_del_pide)
    tras_la_primera = [nodo.id for nodo in await carga.arbol.list_tree(version_id)]

    segunda = await cargar_pide(ruta_del_pide, version_id, carga.arbol)

    assert primera.nodos_creados == TOTAL_QUE_IMPRIME_EL_DOCUMENTO
    assert primera.nodos_omitidos == 0
    assert segunda.nodos_creados == 0
    assert segunda.nodos_omitidos == primera.nodos_creados
    assert [nodo.id for nodo in await carga.arbol.list_tree(version_id)] == tras_la_primera


async def test_el_arbol_cargado_tiene_los_cinco_ejes_y_el_conteo_de_cada_nivel(
    carga, ruta_del_pide
):
    version_id, _ = await _cargar(carga, ruta_del_pide)

    cargados = await carga.arbol.list_tree(version_id)

    assert Counter(nodo.kind for nodo in cargados) == NODOS_QUE_IMPRIME_EL_DOCUMENTO


async def test_cada_nivel_cuelga_del_nivel_de_arriba_y_no_del_eje(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)
    cargados = await carga.arbol.list_tree(version_id)
    por_id = {nodo.id: nodo for nodo in cargados}

    de_quien_cuelga = Counter(
        (nodo.kind, por_id[nodo.parent_id].kind if nodo.parent_id is not None else None)
        for nodo in cargados
    )

    assert de_quien_cuelga == {
        (nivel, PADRE_DE_CADA_NIVEL[nivel]): cuantos
        for nivel, cuantos in NODOS_QUE_IMPRIME_EL_DOCUMENTO.items()
    }


async def test_los_ancestros_de_una_accion_son_los_que_imprime_el_documento(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)
    por_clave = {nodo.key: nodo for nodo in await carga.arbol.list_tree(version_id)}

    leidos = {
        clave: [
            (nodo.key, nodo.kind, nodo.name)
            for nodo in await carga.arbol.ancestors(por_clave[clave].id)
        ]
        for clave in ANCESTROS_QUE_IMPRIME_EL_DOCUMENTO
    }

    assert leidos == ANCESTROS_QUE_IMPRIME_EL_DOCUMENTO


async def test_la_formula_del_indicador_es_la_que_imprime_el_documento(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)
    por_clave = {nodo.key: nodo for nodo in await carga.arbol.list_tree(version_id)}

    leidos = {
        clave: (por_clave[clave].name, por_clave[clave].indicator_formula)
        for clave in INDICADORES_QUE_IMPRIME_EL_DOCUMENTO
    }

    assert leidos == INDICADORES_QUE_IMPRIME_EL_DOCUMENTO


async def test_la_formula_vive_en_la_accion_y_en_ningun_otro_nivel(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)

    con_formula = [
        nodo
        for nodo in await carga.arbol.list_tree(version_id)
        if nodo.indicator_formula is not None
    ]

    assert {nodo.kind for nodo in con_formula} == {ACCION}
    assert len(con_formula) == NODOS_QUE_IMPRIME_EL_DOCUMENTO[ACCION]


async def test_los_objetivos_generales_son_el_parrafo_y_no_la_etiqueta(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)

    generales = [
        nodo for nodo in await carga.arbol.list_tree(version_id) if nodo.kind is OBJETIVO_GENERAL
    ]

    assert (
        len({nodo.name for nodo in generales})
        == NODOS_QUE_IMPRIME_EL_DOCUMENTO[OBJETIVO_GENERAL]
    )
    assert not any("Objetivo General" in nodo.name for nodo in generales)
    assert min(len(nodo.name) for nodo in generales) > 150


async def test_el_orden_entre_hermanos_es_el_del_documento(carga, ruta_del_pide):
    version_id, _ = await _cargar(carga, ruta_del_pide)
    cargados = await carga.arbol.list_tree(version_id)
    por_clave = {nodo.key: nodo for nodo in cargados}

    def hijos_de(clave):
        padre_id = por_clave[clave].id if clave is not None else None
        return [(nodo.key, nodo.order) for nodo in cargados if nodo.parent_id == padre_id]

    assert hijos_de(None) == [("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)]
    assert hijos_de("1.1.1.2") == [
        ("1.1.1.2.1", 1),
        ("1.1.1.2.2", 2),
        ("1.1.1.2.3", 3),
        ("1.1.1.2.4", 4),
        ("1.1.1.2.5", 5),
        ("1.1.1.2.6", 6),
    ]
    assert hijos_de("5.1") == [
        ("5.1.1", 1),
        ("5.1.2", 2),
        ("5.1.3", 3),
        ("5.1.4", 4),
        ("5.1.5", 5),
        ("5.1.6", 6),
    ]


async def test_el_punto_final_de_la_clave_se_recorta_y_la_cadena_no_se_parte(carga, tmp_path):
    ruta = _escribir(tmp_path, SEMILLA_CON_PUNTOS_ALTERNADOS)

    version_id, resumen = await _cargar(carga, ruta)

    cargados = await carga.arbol.list_tree(version_id)
    assert [nodo.key for nodo in cargados] == CLAVES_SIN_EL_PUNTO_FINAL
    assert resumen.nodos_creados == len(CLAVES_SIN_EL_PUNTO_FINAL)
    assert [nodo.parent_id for nodo in cargados] == [None] + [
        nodo.id for nodo in cargados[:-1]
    ]


async def test_un_invisible_de_la_semilla_no_entra_ni_le_tapa_el_punto_final_a_la_clave(
    carga, tmp_path
):
    ruta = _escribir(tmp_path, SEMILLA_CON_INVISIBLES)

    version_id, resumen = await _cargar(carga, ruta)

    cargados = await carga.arbol.list_tree(version_id)
    assert [(nodo.key, nodo.name, nodo.indicator_formula) for nodo in cargados] == [
        ("8", "Eje con invisibles", None),
        ("8.1", "Accion con invisibles", "A / B x 100"),
    ]
    assert resumen.nodos_creados == 2


async def test_un_padre_que_la_semilla_no_define_antes_se_rechaza_nombrandolo(carga, tmp_path):
    ruta = _escribir(tmp_path, SEMILLA_CON_UN_PADRE_QUE_NO_ESTA)
    version_id = await _version_de(carga, ruta)

    with pytest.raises(ValidationError) as rechazo:
        await cargar_pide(ruta, version_id, carga.arbol)

    assert "8.1.1" in rechazo.value.message
    assert "8.1»" in rechazo.value.message
    assert [nodo.key for nodo in await carga.arbol.list_tree(version_id)] == ["8"]


async def test_busca_o_crea_el_instrumento_y_su_version(carga, ruta_del_pide):
    primera = await _version_de(carga, ruta_del_pide)
    segunda = await _version_de(carga, ruta_del_pide)

    assert primera == segunda
    codigo = leer_semilla(ruta_del_pide)["instrumento"]["codigo"]
    creados = [
        instrumento
        for instrumento in await carga.instrumentos.list(active_only=False)
        if instrumento.code == codigo
    ]
    assert len(creados) == 1


async def test_el_codigo_del_instrumento_se_busca_como_queda_guardado(carga, tmp_path):
    declarado = json.loads(json.dumps(SEMILLA_CON_PUNTOS_ALTERNADOS))
    declarado["instrumento"]["codigo"] = f"  t{uuid4().hex[:8]}  "
    declarado["instrumento"]["nombre"] = f"Instrumento en minuscula {uuid4().hex[:8]}"
    ruta = tmp_path / f"minuscula-{uuid4().hex[:8]}.json"
    ruta.write_text(json.dumps(declarado, ensure_ascii=False), encoding="utf-8")

    primera = await _version_de(carga, ruta)
    segunda = await _version_de(carga, ruta)

    assert primera == segunda
    creados = [
        instrumento
        for instrumento in await carga.instrumentos.list(active_only=False)
        if instrumento.code == declarado["instrumento"]["codigo"].strip().upper()
    ]
    assert len(creados) == 1


async def test_la_version_guarda_el_origen_que_declara_la_semilla(carga, ruta_del_pide):
    declarada = leer_semilla(ruta_del_pide)["version"]
    await _version_de(carga, ruta_del_pide)
    instrumento = await _instrumento_de(carga, ruta_del_pide)

    version = await carga.versiones.get_by_label(instrumento.id, declarada["etiqueta"])

    assert version is not None
    assert version.origin == declarada["origen"]
    assert version.effective_from.isoformat() == declarada["vigente_desde"]
    assert version.instrument_id == instrumento.id


async def test_la_version_no_se_confunde_con_la_de_otro_instrumento(carga, tmp_path):
    una = _escribir(tmp_path, SEMILLA_CON_PUNTOS_ALTERNADOS)
    otra = _escribir(tmp_path, SEMILLA_CON_PUNTOS_ALTERNADOS)

    version_de_una = await _version_de(carga, una)
    version_de_otra = await _version_de(carga, otra)

    assert version_de_una != version_de_otra
    instrumento = await _instrumento_de(carga, una)
    assert (await carga.versiones.get_by_label(instrumento.id, "V1")).id == version_de_una
    assert await carga.versiones.get_by_label(instrumento.id, "V2") is None


async def test_la_etiqueta_repetida_en_el_mismo_instrumento_choca(carga, ruta_del_pide):
    etiqueta = leer_semilla(ruta_del_pide)["version"]["etiqueta"]
    version_id = await _version_de(carga, ruta_del_pide)
    instrumento = await _instrumento_de(carga, ruta_del_pide)

    with pytest.raises(ConflictError) as choque:
        await carga.versiones.add(
            InstrumentVersion.create(
                instrument_id=instrumento.id,
                label=etiqueta,
                effective_from=date(2026, 1, 1),
            )
        )

    assert etiqueta in choque.value.message
    assert (await carga.versiones.get_by_label(instrumento.id, etiqueta)).id == version_id


async def test_la_version_de_un_instrumento_que_no_existe_no_se_reporta_como_etiqueta_repetida(
    carga_postgresql,
):
    with pytest.raises(ValidationError) as rechazo:
        await carga_postgresql.versiones.add(
            InstrumentVersion.create(
                instrument_id=INSTRUMENTO_QUE_NADIE_CREO,
                label="V1",
                effective_from=date(2025, 1, 1),
            )
        )

    assert "instrumento" in rechazo.value.message.lower()
    assert "etiqueta" not in rechazo.value.message.lower()


async def test_el_comando_carga_el_pide_en_una_base_recien_migrada(
    base_recien_nacida, monkeypatch, capsys  # noqa: F811
):
    _migrar(base_recien_nacida, "head")
    recien_migrada = dict((await _consultar(base_recien_nacida, CONTEOS_DE_LA_CARGA))[0])
    assert recien_migrada == {"instrumentos": 0, "versiones": 0, "nodos": 0, "con_formula": 0}
    monkeypatch.setattr(sys, "argv", ["cargar_pide", "--database-url", base_recien_nacida])

    primera = await asyncio.to_thread(main)
    segunda = await asyncio.to_thread(main)

    assert (primera, segunda) == (0, 0)
    dicho = capsys.readouterr().out
    assert f"Nodos creados: {TOTAL_QUE_IMPRIME_EL_DOCUMENTO}." in dicho
    assert f"Nodos que ya estaban: {TOTAL_QUE_IMPRIME_EL_DOCUMENTO}." in dicho
    assert dict((await _consultar(base_recien_nacida, CONTEOS_DE_LA_CARGA))[0]) == {
        "instrumentos": 1,
        "versiones": 1,
        "nodos": TOTAL_QUE_IMPRIME_EL_DOCUMENTO,
        "con_formula": NODOS_QUE_IMPRIME_EL_DOCUMENTO[ACCION],
    }


LA_DE_LA_APLICACION = "postgresql+asyncpg://planeacion:clave@localhost:5433/planeacion"

OTRAS_URLS = {
    "la_misma_con_otra_contrasena": (
        "postgresql+asyncpg://otro:otra@localhost:5433/planeacion",
        True,
    ),
    "otro_nombre_de_base": (
        "postgresql+asyncpg://planeacion:clave@localhost:5433/planeacion_test",
        False,
    ),
    "otro_servidor": ("postgresql+asyncpg://planeacion:clave@otro-host:5433/planeacion", False),
    "otro_puerto": ("postgresql+asyncpg://planeacion:clave@localhost:5544/planeacion", False),
    "sin_url_configurada": (None, False),
    "una_url_que_no_se_puede_leer": ("esto no es una url", False),
}


def test_la_url_configurada_sale_del_entorno_antes_que_del_archivo(tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text(f'DATABASE_URL="{LA_DE_LA_APLICACION}"\n', encoding="utf-8")

    assert url_de_la_base_del_entorno({}, archivo) == LA_DE_LA_APLICACION
    assert url_de_la_base_del_entorno({"DATABASE_URL": "la del entorno"}, archivo) == (
        "la del entorno"
    )
    assert url_de_la_base_del_entorno({}, tmp_path / "no-esta") is None


@pytest.mark.parametrize("caso", list(OTRAS_URLS))
def test_la_misma_base_es_el_mismo_servidor_y_el_mismo_nombre(caso):
    otra, es_la_misma = OTRAS_URLS[caso]

    assert es_la_misma_base(LA_DE_LA_APLICACION, otra) is es_la_misma
    assert es_la_misma_base(LA_DE_LA_APLICACION, LA_DE_LA_APLICACION) is True


def _sin_tocar_la_base(monkeypatch, tmp_path, configurada: str):
    archivo = tmp_path / ".env"
    archivo.write_text(f"DATABASE_URL={configurada}\n", encoding="utf-8")
    monkeypatch.setattr("app.scripts.cargar_pide.ARCHIVO_ENV", archivo)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    tocadas: list[str] = []

    async def _registrar(database_url, ruta_json):
        tocadas.append(database_url)
        return ResumenCarga(nodos_creados=0, nodos_omitidos=0)

    monkeypatch.setattr("app.scripts.cargar_pide.cargar_en", _registrar)
    return tocadas


def test_cargar_sobre_la_base_de_la_aplicacion_dice_que_toca_y_exige_confirmar(
    monkeypatch, capsys, tmp_path
):
    tocadas = _sin_tocar_la_base(monkeypatch, tmp_path, LA_DE_LA_APLICACION)
    monkeypatch.setattr(sys, "argv", ["cargar_pide", "--database-url", LA_DE_LA_APLICACION])

    sin_confirmar = main()
    dicho = capsys.readouterr().err
    sin_tocar_nada = list(tocadas)
    monkeypatch.setattr(
        sys, "argv", ["cargar_pide", "--database-url", LA_DE_LA_APLICACION, "--confirmar"]
    )
    confirmando = main()

    assert sin_confirmar == CARGA_SIN_CONFIRMAR
    assert sin_tocar_nada == []
    assert "planeacion en localhost:5433" in dicho
    assert f"{TOTAL_QUE_IMPRIME_EL_DOCUMENTO} nodos" in dicho
    assert "--confirmar" in dicho
    assert confirmando == 0
    assert tocadas == [LA_DE_LA_APLICACION]


def test_cargar_sobre_otra_base_no_exige_confirmar(monkeypatch, capsys, tmp_path):
    otra = OTRAS_URLS["otro_nombre_de_base"][0]
    tocadas = _sin_tocar_la_base(monkeypatch, tmp_path, LA_DE_LA_APLICACION)
    monkeypatch.setattr(sys, "argv", ["cargar_pide", "--database-url", otra])

    salida = main()

    assert salida == 0
    assert tocadas == [otra]
    assert capsys.readouterr().err == ""


async def test_la_carga_no_escribe_nodos_fuera_de_su_version(carga_postgresql, ruta_del_pide):
    version_id, _ = await _cargar(carga_postgresql, ruta_del_pide)

    fuera = (
        await carga_postgresql.conexion.execute(
            text("SELECT count(*) FROM nodos_estrategicos WHERE version_id <> :version"),
            {"version": version_id},
        )
    ).scalar_one()

    assert fuera == 0
