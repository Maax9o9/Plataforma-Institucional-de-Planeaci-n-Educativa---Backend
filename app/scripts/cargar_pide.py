from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.modules.institutional_catalogs.domain.entities import Instrument, InstrumentVersion
from app.modules.institutional_catalogs.domain.ports.repositories import (
    InstrumentRepository,
    InstrumentVersionRepository,
)
from app.modules.institutional_catalogs.domain.ports.strategic_tree_repository import (
    StrategicTreeRepository,
)
from app.modules.institutional_catalogs.domain.strategic_tree_entities import StrategicNode
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyInstrumentRepository,
    SqlAlchemyInstrumentVersionRepository,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)
from app.shared.domain.captured_text import recortado_sin_invisibles
from app.shared.domain.exceptions import AppError, ValidationError
from app.shared.infrastructure.db.session import create_database

SEMILLA_DEL_PIDE = Path(__file__).resolve().parents[2] / "bd" / "semillas" / "pide-2025-2030.json"


@dataclass(frozen=True)
class ResumenCarga:
    nodos_creados: int
    nodos_omitidos: int


def clave_sin_el_punto_final(clave: str) -> str:
    return recortado_sin_invisibles(clave).rstrip(".")


def leer_semilla(ruta_json: Path | str) -> dict[str, Any]:
    return json.loads(Path(ruta_json).read_text(encoding="utf-8"))


async def cargar_pide(
    ruta_json: Path | str,
    version_id: int,
    repositorio: StrategicTreeRepository,
) -> ResumenCarga:
    semilla = leer_semilla(ruta_json)
    ya_estaba = {
        (nodo.parent_id, nodo.key): nodo
        for nodo in await repositorio.list_tree(version_id, include_inactive=True)
    }
    id_por_clave: dict[str, int] = {}
    hermanos_por_padre: dict[int | None, int] = {}
    creados = 0
    omitidos = 0
    for crudo in semilla["nodos"]:
        clave = clave_sin_el_punto_final(crudo["clave"])
        padre_id = _padre_de(crudo, id_por_clave)
        hermanos_por_padre[padre_id] = hermanos_por_padre.get(padre_id, 0) + 1
        guardado = ya_estaba.get((padre_id, clave))
        if guardado is not None:
            id_por_clave[clave] = guardado.id
            omitidos += 1
            continue
        nodo = StrategicNode(
            version_id=version_id,
            parent_id=padre_id,
            kind=crudo["nivel"],
            key=clave,
            name=crudo["denominacion"],
            order=hermanos_por_padre[padre_id],
            indicator_formula=crudo.get("formula_indicador"),
        )
        await repositorio.add(nodo)
        id_por_clave[clave] = nodo.id
        creados += 1
    return ResumenCarga(nodos_creados=creados, nodos_omitidos=omitidos)


def _padre_de(crudo: dict[str, Any], id_por_clave: dict[str, int]) -> int | None:
    declarado = crudo["padre"]
    if declarado is None:
        return None
    padre = clave_sin_el_punto_final(declarado)
    if padre not in id_por_clave:
        raise ValidationError(
            f"«{crudo['clave']}» cuelga de «{declarado}», que la semilla no define antes."
        )
    return id_por_clave[padre]


async def asegurar_version(
    ruta_json: Path | str,
    instrumentos: InstrumentRepository,
    versiones: InstrumentVersionRepository,
) -> int:
    semilla = leer_semilla(ruta_json)
    instrumento = await _asegurar_instrumento(instrumentos, semilla["instrumento"])
    declarada = semilla["version"]
    version = await versiones.get_by_label(instrumento.id, declarada["etiqueta"])
    if version is None:
        version = InstrumentVersion.create(
            instrument_id=instrumento.id,
            label=declarada["etiqueta"],
            effective_from=date.fromisoformat(declarada["vigente_desde"]),
            origin=declarada.get("origen"),
        )
        await versiones.add(version)
    return version.id


async def _asegurar_instrumento(
    instrumentos: InstrumentRepository, declarado: dict[str, Any]
) -> Instrument:
    codigo = declarado["codigo"].strip().upper()
    for guardado in await instrumentos.list(active_only=False):
        if guardado.code == codigo:
            return guardado
    nuevo = Instrument.create(
        code=codigo,
        name=declarado["nombre"],
        description=declarado.get("descripcion"),
    )
    await instrumentos.add(nuevo)
    return nuevo


async def cargar_en(database_url: str, ruta_json: Path | str) -> ResumenCarga:
    engine, session_factory = create_database(
        Settings(database_url=database_url, database_echo=False)
    )
    if engine is None or session_factory is None:
        raise ValidationError("La URL de la base de datos es obligatoria para cargar el PIDE.")
    try:
        version_id = await asegurar_version(
            ruta_json,
            SqlAlchemyInstrumentRepository(session_factory),
            SqlAlchemyInstrumentVersionRepository(session_factory),
        )
        return await cargar_pide(
            ruta_json, version_id, SqlAlchemyStrategicTreeRepository(session_factory)
        )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Carga el arbol del PIDE 2025-2030 en una version del instrumento."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--semilla", default=str(SEMILLA_DEL_PIDE))
    args = parser.parse_args()
    try:
        resumen = asyncio.run(cargar_en(args.database_url, Path(args.semilla)))
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"La carga no se pudo completar en PostgreSQL: {exc}", file=sys.stderr)
        return 1
    print(
        f"Nodos creados: {resumen.nodos_creados}. "
        f"Nodos que ya estaban: {resumen.nodos_omitidos}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
