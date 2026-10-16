"""El modulo de indicadores del PIDE queda dormido mientras el trabajo se
concentra en el POA.

Lo que se apaga es la superficie HTTP, no el modulo: el POA importa de el
`CaptureStatus`, `StateChange` y los exportadores de reportes, asi que borrarlo
romperia el ciclo de revision cuatrimestral. Estas pruebas fijan esa frontera
para que encender o apagar el modulo sea una decision explicita y no el efecto
lateral de un `include_router` suelto.
"""

from __future__ import annotations

from app.core.app_factory import create_app
from app.core.config import Settings

#: Endpoints que sostiene el modulo dormido.
RUTAS_PIDE = (
    "/api/v1/indicadores",
    "/api/v1/capturas",
    "/api/v1/config/semaforos",
    "/api/v1/reportes/pide",
    "/api/v1/dashboards/planeacion",
)

#: Endpoints que el POA necesita y que no pueden caerse con el apagado.
RUTAS_POA = (
    "/api/v1/poa/cedulas",
    "/api/v1/poa/seguimientos",
    "/api/v1/periodos",
    "/api/v1/evidencias",
    "/api/v1/bitacora",
    "/api/v1/catalogos/areas",
)

#: El historial del indicador vive bajo /indicadores pero lo sirve el router de
#: auditoria, que se queda: es parte de la bitacora, no del modulo del PIDE.
EXCEPCION_AUDITORIA = "/api/v1/indicadores/{indicator_id}/historial"


def _settings(**extra) -> Settings:
    return Settings(
        environment="testing",
        secret_key="test-secret-key-with-more-than-32-characters",
        database_url=None,
        email_provider="console",
        **extra,
    )


def _rutas(**extra) -> set[str]:
    return set(create_app(_settings(**extra)).openapi()["paths"])


def test_por_omision_el_pide_no_se_publica():
    rutas = _rutas()

    vivas = [r for r in rutas if r.startswith(RUTAS_PIDE) and r != EXCEPCION_AUDITORIA]
    assert vivas == [], vivas


def test_el_historial_del_indicador_sobrevive_porque_es_bitacora():
    assert EXCEPCION_AUDITORIA in _rutas()


def test_el_poa_y_su_andamio_siguen_publicados():
    rutas = _rutas()

    for esperada in RUTAS_POA:
        assert any(r.startswith(esperada) for r in rutas), esperada


def test_apagar_el_pide_encoge_la_api_a_la_mitad():
    """Si el numero no baja, el apagado no esta haciendo nada."""
    dormido = _rutas()
    despierto = _rutas(indicators_module_enabled=True)

    assert len(dormido) < len(despierto)
    assert dormido < despierto


def test_la_bandera_vuelve_a_encender_el_pide():
    rutas = _rutas(indicators_module_enabled=True)

    for esperada in RUTAS_PIDE:
        assert any(r.startswith(esperada) for r in rutas), esperada


def test_el_poa_sigue_importando_del_modulo_dormido():
    """Si esto falla, el modulo dejo de ser importable y el POA se rompe."""
    from app.modules.indicators_capture.domain.value_objects import CaptureStatus
    from app.modules.indicators_validation.domain.entities import StateChange
    from app.modules.poa_planning.domain.cedula_entities import PoaActivityFollowUp

    assert PoaActivityFollowUp.__annotations__["status"] is not None
    assert CaptureStatus.DRAFT and StateChange
