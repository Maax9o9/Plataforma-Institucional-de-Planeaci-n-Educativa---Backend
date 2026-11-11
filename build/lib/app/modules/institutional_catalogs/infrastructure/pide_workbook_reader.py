from __future__ import annotations

import io
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.shared.domain.exceptions import UnsupportedMediaTypeError

from ..domain.pide_workbook import (
    HOJA_DE_ACCIONES,
    HOJA_DE_OBJETIVOS,
    FilaDeAcciones,
    FilaDeObjetivos,
    WorkbookShapeError,
    limpio,
)

COLUMNAS_DE_ACCIONES = 4
COLUMNAS_DE_OBJETIVOS = 4

COLUMNAS_COMBINADAS_DE_ACCIONES = (0, 1)
COLUMNAS_COMBINADAS_DE_OBJETIVOS = (0, 1)

NO_ES_UN_LIBRO = (
    "El archivo no se pudo abrir como libro de Excel. Envíe el .xlsx que acordó el área."
)


def filas_del_libro(contenido: bytes) -> tuple[list[FilaDeAcciones], list[FilaDeObjetivos]]:
    try:
        libro = load_workbook(io.BytesIO(contenido), data_only=True)
    except (BadZipFile, KeyError, ValueError, OSError):
        raise UnsupportedMediaTypeError(NO_ES_UN_LIBRO) from None

    try:
        acciones = [
            FilaDeAcciones(
                numero=numero,
                eje=celdas[0],
                linea=celdas[1],
                accion=celdas[2],
                indicador=celdas[3],
            )
            for numero, celdas in _celdas(
                _hoja(libro, HOJA_DE_ACCIONES),
                COLUMNAS_DE_ACCIONES,
                COLUMNAS_COMBINADAS_DE_ACCIONES,
            )
        ]
        objetivos: list[FilaDeObjetivos] = []
        if HOJA_DE_OBJETIVOS in libro.sheetnames:
            objetivos = [
                FilaDeObjetivos(
                    numero=numero,
                    eje=celdas[0],
                    objetivo_general=celdas[1],
                    clave_especifico=celdas[2],
                    objetivo_especifico=celdas[3],
                )
                for numero, celdas in _celdas(
                    libro[HOJA_DE_OBJETIVOS],
                    COLUMNAS_DE_OBJETIVOS,
                    COLUMNAS_COMBINADAS_DE_OBJETIVOS,
                )
            ]
    finally:
        libro.close()

    return acciones, objetivos


def _hoja(libro: Workbook, nombre: str) -> Worksheet:
    if nombre not in libro.sheetnames:
        tiene = ", ".join(f"«{hoja}»" for hoja in libro.sheetnames) or "ninguna"
        raise WorkbookShapeError(
            f"El libro no trae la hoja «{nombre}», que es la que se carga. Trae: {tiene}."
        )
    return libro[nombre]


def _celdas(
    hoja: Worksheet, cuantas_columnas: int, combinadas: tuple[int, ...]
) -> list[tuple[int, list[str | None]]]:
    arrastre: dict[int, str | None] = dict.fromkeys(combinadas)
    filas: list[tuple[int, list[str | None]]] = []
    for numero, valores in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
        propias = [
            limpio(valores[columna]) if columna < len(valores) else None
            for columna in range(cuantas_columnas)
        ]
        if all(celda is None for celda in propias):
            continue
        celdas: list[str | None] = []
        for columna, propia in enumerate(propias):
            if columna not in combinadas:
                celdas.append(propia)
                continue
            if propia is not None:
                arrastre[columna] = propia
            celdas.append(arrastre[columna])
        filas.append((numero, celdas))
    return filas
