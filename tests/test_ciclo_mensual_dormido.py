from __future__ import annotations

import re
import warnings
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.dashboards.api.router import router as tableros_router
from app.modules.indicators_capture.api.router import router as captura_router
from app.modules.indicators_catalog.api.router import router as catalogo_router
from app.modules.indicators_reports.api.router import router as reportes_router
from app.modules.indicators_scoring.api.router import router as puntajes_router
from app.modules.indicators_validation.api.router import router as validacion_router

#: Endpoints que el POA necesita y que no pueden caerse con el apagado.
RUTAS_POA = (
    "/api/v1/poa/cedulas",
    "/api/v1/poa/seguimientos",
    "/api/v1/periodos",
    "/api/v1/evidencias",
    "/api/v1/bitacora",
    "/api/v1/catalogos/areas",
)

HISTORIAL_QUE_SIRVE_LA_BITACORA = "/api/v1/indicadores/{indicator_id}/historial"

ROUTERS_DEL_CICLO_MENSUAL = {
    "captura": captura_router,
    "validacion": validacion_router,
    "puntajes": puntajes_router,
    "reportes": reportes_router,
    "tableros": tableros_router,
}

POR_ROUTER = pytest.mark.parametrize(
    "router", ROUTERS_DEL_CICLO_MENSUAL.values(), ids=ROUTERS_DEL_CICLO_MENSUAL.keys()
)


def _settings(**extra) -> Settings:
    return Settings(
        environment="testing",
        secret_key="test-secret-key-with-more-than-32-characters",
        database_url=None,
        email_provider="console",
        **extra,
    )


def _publicadas(**extra) -> set[tuple[str, str]]:
    rutas = create_app(_settings(**extra)).openapi()["paths"]
    return {(metodo, ruta) for ruta, metodos in rutas.items() for metodo in metodos}


def _rutas(**extra) -> set[str]:
    return {ruta for _, ruta in _publicadas(**extra)}


def _operaciones(router) -> set[tuple[str, str]]:
    prefijo = _settings().api_v1_prefix
    operaciones = {
        (metodo.lower(), f"{prefijo}{ruta.path}")
        for ruta in router.routes
        for metodo in ruta.methods
    }
    assert operaciones
    return operaciones


def _consulta(router) -> str:
    ruta = next(ruta.path for ruta in router.routes if "GET" in ruta.methods)
    return _settings().api_v1_prefix + re.sub(r"\{[^}]+\}", str(uuid4()), ruta)


@pytest.fixture
async def cliente_por_omision():
    async with AsyncClient(
        transport=ASGITransport(app=create_app(_settings())), base_url="http://testserver"
    ) as cliente:
        yield cliente


@pytest.mark.parametrize("variable", ["MONTHLY_CYCLE_ENABLED", "INDICATORS_MODULE_ENABLED"])
def test_la_bandera_responde_al_nombre_nuevo_y_al_que_pueda_estar_en_un_despliegue(
    monkeypatch, variable
):
    monkeypatch.setenv(variable, "true")

    assert _settings().monthly_cycle_enabled is True
    assert set().union(
        *(_operaciones(router) for router in ROUTERS_DEL_CICLO_MENSUAL.values())
    ) <= _publicadas()


def test_el_catalogo_de_indicadores_se_publica_por_omision():
    assert _operaciones(catalogo_router) <= _publicadas()


@POR_ROUTER
def test_por_omision_los_routers_del_ciclo_mensual_no_se_publican(router):
    assert _operaciones(router) & _publicadas() == set()


def test_la_bandera_enciende_exactamente_el_ciclo_mensual():
    dormido = _publicadas()
    despierto = _publicadas(monthly_cycle_enabled=True)

    assert dormido <= despierto
    assert despierto - dormido == set().union(
        *(_operaciones(router) for router in ROUTERS_DEL_CICLO_MENSUAL.values())
    )


@pytest.mark.parametrize("encendido", [False, True], ids=["dormido", "despierto"])
def test_ninguna_operacion_se_declara_dos_veces(encendido):
    aplicacion = create_app(_settings(monthly_cycle_enabled=encendido))

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Duplicate Operation ID")
        aplicacion.openapi()


async def test_el_catalogo_responde_sin_la_bandera_y_pide_sesion(cliente_por_omision):
    respuesta = await cliente_por_omision.get(_consulta(catalogo_router))

    assert respuesta.status_code == 401


@POR_ROUTER
async def test_el_ciclo_mensual_sigue_devolviendo_404(cliente_por_omision, router):
    respuesta = await cliente_por_omision.get(_consulta(router))

    assert respuesta.status_code == 404


def test_el_historial_del_indicador_sobrevive_porque_es_bitacora():
    assert HISTORIAL_QUE_SIRVE_LA_BITACORA in _rutas()


def test_el_poa_y_su_andamio_siguen_publicados():
    rutas = _rutas()

    for esperada in RUTAS_POA:
        assert any(r.startswith(esperada) for r in rutas), esperada


def test_el_poa_sigue_importando_del_modulo_dormido():
    """Si esto falla, el modulo dejo de ser importable y el POA se rompe."""
    from app.modules.indicators_capture.domain.value_objects import CaptureStatus
    from app.modules.indicators_validation.domain.entities import StateChange
    from app.modules.poa_planning.domain.cedula_entities import PoaActivityFollowUp

    assert PoaActivityFollowUp.__annotations__["status"] is not None
    assert CaptureStatus.DRAFT and StateChange
