"""Pruebas de los ajustes P0 de la revision 0.3 del contrato.

Cubren los tres puntos que el frontend reporto como datos falsos o riesgo de
perdida de informacion: el filtro de periodicidad que se ignoraba, la bitacora
que no conservaba el autor, y el arranque en produccion sin base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.audit.domain.entities import AuditEntry
from app.modules.audit.infrastructure.repository import InMemoryAuditRepository
from app.modules.audit.infrastructure.subscriber import register_audit_subscriber
from app.shared.domain.domain_event import DomainEvent
from app.shared.infrastructure.events.in_memory_event_bus import InMemoryEventBus


def _settings(**overrides) -> Settings:
    base = {
        "environment": "testing",
        "secret_key": "test-secret-key-with-more-than-32-characters",
        "database_url": None,
        "email_provider": "console",
        "cors_origins": ["http://localhost:5173"],
    }
    base.update(overrides)
    return Settings(**base)


# --- Arranque sin base de datos -------------------------------------------


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_ambiente_compartido_exige_database_url(environment: str) -> None:
    """Sin DATABASE_URL el contenedor usaria repositorios en memoria.

    En un ambiente compartido eso arranca sano, responde 200 y pierde toda la
    informacion al reiniciar. Debe fallar al arrancar.
    """
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app(_settings(
            environment=environment,
            refresh_cookie_secure=True,
            database_url=None,
        ))


def test_desarrollo_conserva_el_fallback_en_memoria() -> None:
    app = create_app(_settings(environment="testing",
            indicators_module_enabled=True, database_url=None))
    assert isinstance(app, FastAPI)


# --- Instantanea del autor en la bitacora ----------------------------------


@dataclass(frozen=True)
class _EventoDePrueba(DomainEvent):
    pass


class _DirectorioFalso:
    """Lector minimo del directorio, con nombre mutable para simular un cambio."""

    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        self.consultas = 0

    async def get_by_id(self, user_id: int):
        self.consultas += 1
        if user_id != 11:
            return None
        return type("Usuario", (), {"id": 11, "full_name": self.nombre})()


async def _emitir(bus: InMemoryEventBus, actor_id: int | None) -> None:
    await bus.publish(_EventoDePrueba(
        actor_id=actor_id,
        aggregate_type="indicator",
        aggregate_id=21,
        action="updated",
        data={"clave": "PIDE-21"},
    ))


@pytest.mark.asyncio
async def test_la_bitacora_congela_el_nombre_del_autor() -> None:
    bus = InMemoryEventBus()
    repositorio = InMemoryAuditRepository()
    directorio = _DirectorioFalso("María López")
    register_audit_subscriber(bus, repositorio, directorio)

    await _emitir(bus, 11)

    # La persona cambia de nombre o el puesto se reasigna.
    directorio.nombre = "Otra Persona"
    await _emitir(bus, 11)

    entradas = await repositorio.list()
    nombres = sorted(entrada.actor_name for entrada in entradas)
    assert nombres == ["María López", "Otra Persona"]


@pytest.mark.asyncio
async def test_un_evento_del_sistema_no_lleva_nombre() -> None:
    bus = InMemoryEventBus()
    repositorio = InMemoryAuditRepository()
    register_audit_subscriber(bus, repositorio, _DirectorioFalso("María López"))

    await _emitir(bus, None)

    entradas = await repositorio.list()
    assert entradas[0].actor_id is None
    assert entradas[0].actor_name is None


@pytest.mark.asyncio
async def test_un_directorio_caido_no_impide_registrar_el_movimiento() -> None:
    """La bitacora nunca debe tumbar la operacion que la origino."""

    class _DirectorioRoto:
        async def get_by_id(self, user_id: int):
            raise RuntimeError("directorio no disponible")

    bus = InMemoryEventBus()
    repositorio = InMemoryAuditRepository()
    register_audit_subscriber(bus, repositorio, _DirectorioRoto())

    await _emitir(bus, 11)

    entradas = await repositorio.list()
    assert len(entradas) == 1
    assert entradas[0].actor_id == 11
    assert entradas[0].actor_name is None


@pytest.mark.asyncio
async def test_sin_directorio_la_entrada_conserva_solo_el_identificador() -> None:
    bus = InMemoryEventBus()
    repositorio = InMemoryAuditRepository()
    register_audit_subscriber(bus, repositorio)

    await _emitir(bus, 11)

    entradas = await repositorio.list()
    assert entradas[0].actor_name is None


def test_la_entrada_expone_el_nombre_en_el_contrato_http() -> None:
    from datetime import UTC, datetime

    from app.modules.audit.api.schemas import EntradaAuditoriaResponse

    respuesta = EntradaAuditoriaResponse.from_domain(AuditEntry(
        id=1,
        event_name="IndicatorUpdated",
        occurred_at=datetime.now(UTC),
        actor_id=11,
        actor_name="María López",
        aggregate_type="indicator",
        aggregate_id=21,
        action="updated",
        data={},
    ))

    assert respuesta.usuario_nombre == "María López"


# --- Filtro de periodicidad ------------------------------------------------


async def _crear_indicador(client, headers, clave: str, periodicidad: str, area_id: int) -> None:
    respuesta = await client.post(
        "/api/v1/indicadores",
        headers=headers,
        json={
            "clave": clave,
            "nombre": f"Indicador {clave}",
            "metodo_calculo": "a / b * 100",
            "unidad_medida": "Porcentaje",
            "area_id": area_id,
            "responsable_id": 1,
            "periodicidad": periodicidad,
        },
    )
    assert respuesta.status_code == 201, respuesta.text


@pytest.mark.asyncio
async def test_la_periodicidad_filtra_y_ajusta_el_total(client, app) -> None:
    """Antes el parametro se aceptaba y se descartaba: devolvia el catalogo entero.

    Un filtro que no filtra es peor que uno ausente: quien elige «anual» y ve
    la lista completa concluye que no hay indicadores anuales.
    """
    from tests.test_ep01_ep05_flow import seed_admin

    await seed_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "planeacion@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={"codigo": "PLN", "nombre": "Planeacion", "tipo": "administrativa"},
    )
    area_id = area.json()["id"]

    await _crear_indicador(client, headers, "MEN-01", "mensual", area_id)
    await _crear_indicador(client, headers, "MEN-02", "mensual", area_id)
    await _crear_indicador(client, headers, "ANU-01", "anual", area_id)

    sin_filtro = await client.get("/api/v1/indicadores", headers=headers)
    assert sin_filtro.json()["total"] == 3

    mensuales = await client.get("/api/v1/indicadores?periodicidad=mensual", headers=headers)
    cuerpo = mensuales.json()
    assert cuerpo["total"] == 2
    assert {item["periodicidad"] for item in cuerpo["items"]} == {"mensual"}

    anuales = await client.get("/api/v1/indicadores?periodicidad=anual", headers=headers)
    assert anuales.json()["total"] == 1

    cuatrimestrales = await client.get(
        "/api/v1/indicadores?periodicidad=cuatrimestral", headers=headers
    )
    assert cuatrimestrales.json()["total"] == 0


@pytest.mark.asyncio
async def test_una_periodicidad_desconocida_se_rechaza(client, app) -> None:
    from tests.test_ep01_ep05_flow import seed_admin

    await seed_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "planeacion@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    respuesta = await client.get("/api/v1/indicadores?periodicidad=INVENTADA", headers=headers)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"]


@pytest.mark.asyncio
async def test_la_periodicidad_se_combina_con_los_demas_filtros(client, app) -> None:
    from tests.test_ep01_ep05_flow import seed_admin

    await seed_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "planeacion@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    primera = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={"codigo": "A1", "nombre": "Area uno", "tipo": "administrativa"},
    )
    segunda = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={"codigo": "A2", "nombre": "Area dos", "tipo": "administrativa"},
    )

    await _crear_indicador(client, headers, "A1-MEN", "mensual", primera.json()["id"])
    await _crear_indicador(client, headers, "A2-MEN", "mensual", segunda.json()["id"])
    await _crear_indicador(client, headers, "A1-ANU", "anual", primera.json()["id"])

    combinado = await client.get(
        f"/api/v1/indicadores?periodicidad=mensual&area_id={primera.json()['id']}",
        headers=headers,
    )
    cuerpo = combinado.json()

    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["clave"] == "A1-MEN"
