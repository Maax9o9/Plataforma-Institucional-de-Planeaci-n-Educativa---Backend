"""Con varios procesos de la API, los recordatorios los genera uno solo.

Cada proceso levanta su propio programador. Sin turno, cuatro procesos mandan
el mismo recordatorio cuatro veces.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.shared.infrastructure.db.turno_exclusivo import (
    ElTurnoSiempreEsMio,
    el_turno_de_los_recordatorios,
)


@pytest.fixture
def fabrica_de_sesiones():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada")
    motor = create_async_engine(url)
    yield async_sessionmaker(motor, expire_on_commit=False)


async def test_sin_base_configurada_el_turno_es_de_quien_pregunta():
    turno = el_turno_de_los_recordatorios(None)

    assert isinstance(turno, ElTurnoSiempreEsMio)
    async with turno.pedir() as me_toca:
        assert me_toca is True


async def test_dos_procesos_piden_el_turno_y_solo_uno_lo_tiene(fabrica_de_sesiones):
    uno = el_turno_de_los_recordatorios(fabrica_de_sesiones)
    otro = el_turno_de_los_recordatorios(fabrica_de_sesiones)

    async with uno.pedir() as primero:
        async with otro.pedir() as segundo:
            assert (primero, segundo) == (True, False)


async def test_al_soltarlo_el_turno_queda_libre_para_el_siguiente(fabrica_de_sesiones):
    uno = el_turno_de_los_recordatorios(fabrica_de_sesiones)
    otro = el_turno_de_los_recordatorios(fabrica_de_sesiones)

    async with uno.pedir() as primero:
        assert primero is True

    async with otro.pedir() as segundo:
        assert segundo is True


async def test_el_turno_se_suelta_aunque_el_trabajo_reviente(fabrica_de_sesiones):
    uno = el_turno_de_los_recordatorios(fabrica_de_sesiones)
    otro = el_turno_de_los_recordatorios(fabrica_de_sesiones)

    with pytest.raises(RuntimeError):
        async with uno.pedir() as me_toca:
            assert me_toca is True
            raise RuntimeError("falló la generación de recordatorios")

    async with otro.pedir() as siguiente:
        assert siguiente is True


class TurnoOcupado:
    def __init__(self) -> None:
        self.preguntas = 0

    def pedir(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def negado():
            self.preguntas += 1
            yield False

        return negado()


async def test_el_proceso_sin_turno_no_hace_la_vuelta(backend_client):
    from app.core.lifecycle import _una_vuelta_de_recordatorios

    app, _ = backend_client
    app.state.turno_de_los_recordatorios = TurnoOcupado()
    reintentos = []
    app.state.notification_service.retry_pending = (
        lambda: reintentos.append(1) or _nada()
    )

    await _una_vuelta_de_recordatorios(app)

    assert app.state.turno_de_los_recordatorios.preguntas == 1
    assert reintentos == []


async def test_el_proceso_con_el_turno_si_hace_la_vuelta(backend_client):
    from app.core.lifecycle import _una_vuelta_de_recordatorios

    app, _ = backend_client
    app.state.turno_de_los_recordatorios = ElTurnoSiempreEsMio()
    reintentos = []
    app.state.notification_service.retry_pending = (
        lambda: reintentos.append(1) or _nada()
    )

    await _una_vuelta_de_recordatorios(app)

    assert reintentos == [1]


async def _nada() -> None:
    return None
