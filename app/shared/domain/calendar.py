"""Calendario institucional independiente de la zona horaria del servidor."""

from datetime import date, datetime
from zoneinfo import ZoneInfo


def institutional_today() -> date:
    return datetime.now(ZoneInfo("America/Mexico_City")).date()
