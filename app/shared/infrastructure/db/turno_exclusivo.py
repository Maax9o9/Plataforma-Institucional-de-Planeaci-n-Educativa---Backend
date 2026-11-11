"""Quién de todos los procesos hace el trabajo de fondo.

La API corre con varios procesos para repartir la carga, y cada uno levanta su
propio programador de recordatorios. Sin un turno, cuatro procesos generan el
mismo recordatorio cuatro veces y la gente recibe cuatro correos iguales.

El turno se pide a PostgreSQL con un candado de aviso: lo toma un solo proceso
—de esta máquina o de otra—, el resto se salta la vuelta y lo vuelve a
intentar en la siguiente. Si la base no está configurada, el turno es siempre
de quien pregunta, que es lo que corresponde a una sola instancia en memoria.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

CLAVE_DE_LOS_RECORDATORIOS = 870_114_001


class ElTurnoSiempreEsMio:
    @asynccontextmanager
    async def pedir(self) -> AsyncIterator[bool]:
        yield True


class ElTurnoLoDaPostgres:
    def __init__(self, session_factory, clave: int = CLAVE_DE_LOS_RECORDATORIOS) -> None:
        self.session_factory = session_factory
        self.clave = clave

    @asynccontextmanager
    async def pedir(self) -> AsyncIterator[bool]:
        async with self.session_factory() as sesion:
            tomado = bool(
                await sesion.scalar(
                    text("SELECT pg_try_advisory_lock(:clave)"), {"clave": self.clave}
                )
            )
            try:
                yield tomado
            finally:
                if tomado:
                    await sesion.execute(
                        text("SELECT pg_advisory_unlock(:clave)"), {"clave": self.clave}
                    )


def el_turno_de_los_recordatorios(session_factory):
    if session_factory is None:
        return ElTurnoSiempreEsMio()
    return ElTurnoLoDaPostgres(session_factory)
