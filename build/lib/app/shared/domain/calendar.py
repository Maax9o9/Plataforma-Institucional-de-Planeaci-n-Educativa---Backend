"""Calendario institucional independiente de la zona horaria del servidor."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def institutional_today() -> date:
    return datetime.now(ZoneInfo("America/Mexico_City")).date()


MESES_DEL_ANIO = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def el_dia_en_letras(dia: date) -> str:
    return f"{dia.day} de {MESES_DEL_ANIO[dia.month - 1]} de {dia.year}"
