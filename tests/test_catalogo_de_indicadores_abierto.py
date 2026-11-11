from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.indicators_catalog.api.router import router as catalogo_router

PREFIJO = "/api/v1"
UN_INDICADOR = 10**6

ESCRITURAS = {
    "registrar": ("POST", "/indicadores"),
    "editar": ("PATCH", "/indicadores/{id}"),
    "desactivar": ("POST", "/indicadores/{id}/desactivar"),
    "linea_base": ("POST", "/indicadores/{id}/linea-base"),
    "metas": ("POST", "/indicadores/{id}/metas"),
    "periodicidad": ("PATCH", "/indicadores/{id}/periodicidad"),
    "criterios_seaes": ("PUT", "/indicadores/{id}/criterios-seaes"),
}

LECTURAS = {
    "listar": ("GET", "/indicadores"),
    "cobertura_seaes": ("GET", "/indicadores/cobertura-seaes"),
    "consultar": ("GET", "/indicadores/{id}"),
    "linea_base": ("GET", "/indicadores/{id}/linea-base"),
    "metas": ("GET", "/indicadores/{id}/metas"),
    "criterios_seaes": ("GET", "/indicadores/{id}/criterios-seaes"),
}

OPERACIONES = {**LECTURAS, **{f"escribir_{nombre}": par for nombre, par in ESCRITURAS.items()}}

ROLES_QUE_ADMINISTRAN_EL_CATALOGO = (Role.PLANEACION, Role.PLANEACION_ADMIN, Role.ADMIN_SISTEMA)
ROLES_SIN_PERMISO_DE_ESCRITURA = tuple(
    rol for rol in Role if rol not in ROLES_QUE_ADMINISTRAN_EL_CATALOGO
)

POR_ESCRITURA = pytest.mark.parametrize("escritura", list(ESCRITURAS))
POR_ROL = pytest.mark.parametrize("rol", list(Role), ids=lambda rol: rol.value)


def _url(metodo_y_plantilla: tuple[str, str]) -> tuple[str, str]:
    metodo, plantilla = metodo_y_plantilla
    return metodo, PREFIJO + plantilla.format(id=UN_INDICADOR)


@pytest.fixture
async def catalogo():
    aplicacion = create_app(
        Settings(
            environment="testing",
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
            bootstrap_admin_email=None,
            bootstrap_admin_password=None,
        )
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=aplicacion), base_url="http://testserver"
        ) as cliente:
            yield aplicacion, cliente
    finally:
        await aplicacion.state.notification_service.close()


async def _cabeceras(aplicacion, cliente, rol: Role) -> dict[str, str]:
    correo = f"catalogo-{rol.value}-{uuid4().hex[:8]}@example.com"
    await CreateUser(
        aplicacion.state.user_repository,
        aplicacion.state.password_hasher,
        aplicacion.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name=f"Catalogo {rol.value}",
            password="password-seguro",
            roles={rol},
            area_id=None,
        )
    )
    entrada = await cliente.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    assert entrada.status_code == 200, entrada.text
    return {"Authorization": f"Bearer {entrada.json()['access_token']}"}


def test_el_catalogo_publica_exactamente_las_operaciones_que_estas_pruebas_vigilan():
    publicadas = {
        (metodo, ruta.path.replace("{indicator_id}", "{id}"))
        for ruta in catalogo_router.routes
        for metodo in ruta.methods
    }

    assert publicadas == set(OPERACIONES.values())
    assert len(OPERACIONES) == len(publicadas) == 13


@pytest.mark.parametrize("operacion", list(OPERACIONES))
async def test_sin_sesion_el_catalogo_contesta_401(catalogo, operacion):
    _, cliente = catalogo
    metodo, url = _url(OPERACIONES[operacion])

    respuesta = await cliente.request(metodo, url, json={})

    assert respuesta.status_code == 401, respuesta.text


@POR_ESCRITURA
@pytest.mark.parametrize("rol", ROLES_SIN_PERMISO_DE_ESCRITURA, ids=lambda rol: rol.value)
async def test_las_escrituras_del_catalogo_las_niega_quien_no_administra(catalogo, rol, escritura):
    aplicacion, cliente = catalogo
    cabeceras = await _cabeceras(aplicacion, cliente, rol)
    metodo, url = _url(ESCRITURAS[escritura])

    respuesta = await cliente.request(metodo, url, headers=cabeceras, json={})

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["code"] == "FORBIDDEN"


@POR_ESCRITURA
@pytest.mark.parametrize(
    "rol", ROLES_QUE_ADMINISTRAN_EL_CATALOGO, ids=lambda rol: rol.value
)
async def test_las_escrituras_del_catalogo_dejan_pasar_a_quien_administra(
    catalogo, rol, escritura
):
    aplicacion, cliente = catalogo
    cabeceras = await _cabeceras(aplicacion, cliente, rol)
    metodo, url = _url(ESCRITURAS[escritura])

    respuesta = await cliente.request(metodo, url, headers=cabeceras, json={})

    assert respuesta.status_code not in (401, 403), respuesta.text


async def _un_indicador_con_umbrales(cliente, cabeceras) -> dict:
    area = await cliente.post(
        "/api/v1/catalogos/areas",
        json={"codigo": f"A{uuid4().hex[:6]}", "nombre": f"Area {uuid4().hex[:6]}"},
        headers=cabeceras,
    )
    assert area.status_code == 201, area.text
    yo = await cliente.get("/api/v1/auth/me", headers=cabeceras)
    assert yo.status_code == 200, yo.text
    creado = await cliente.post(
        f"{PREFIJO}/indicadores",
        json={
            "clave": f"IND-{uuid4().hex[:6]}",
            "nombre": "Cobertura educativa",
            "metodo_calculo": "Resultado / meta * 100",
            "unidad_medida": "Porcentaje",
            "area_id": area.json()["id"],
            "responsable_id": yo.json()["id"],
            "periodicidad": "mensual",
            "umbral_verde_min": 90,
            "umbral_amarillo_min": 70,
        },
        headers=cabeceras,
    )
    assert creado.status_code == 201, creado.text
    return creado.json()


@pytest.mark.parametrize("umbral", ["umbral_verde_min", "umbral_amarillo_min"])
async def test_el_patch_rechaza_un_umbral_en_vez_de_contestar_200_sin_cambiarlo(catalogo, umbral):
    aplicacion, cliente = catalogo
    cabeceras = await _cabeceras(aplicacion, cliente, Role.PLANEACION)
    indicador = await _un_indicador_con_umbrales(cliente, cabeceras)
    ruta = f"{PREFIJO}/indicadores/{indicador['id']}"

    con_el_umbral = await cliente.patch(
        ruta, json={"nombre": "Cobertura corregida", umbral: 50}, headers=cabeceras
    )
    el_umbral_solo = await cliente.patch(ruta, json={umbral: 50}, headers=cabeceras)
    sin_el_umbral = await cliente.patch(
        ruta, json={"nombre": "Cobertura corregida"}, headers=cabeceras
    )

    assert con_el_umbral.status_code == 422, con_el_umbral.text
    assert con_el_umbral.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert el_umbral_solo.status_code == 422, el_umbral_solo.text
    assert sin_el_umbral.status_code == 200, sin_el_umbral.text
    assert sin_el_umbral.json()["nombre"] == "Cobertura corregida"
    assert sin_el_umbral.json()[umbral] == indicador[umbral]


@POR_ROL
async def test_las_lecturas_del_catalogo_las_abre_cualquier_rol_autenticado(catalogo, rol):
    aplicacion, cliente = catalogo
    cabeceras = await _cabeceras(aplicacion, cliente, rol)

    negadas = {}
    for nombre, operacion in LECTURAS.items():
        metodo, url = _url(operacion)
        respuesta = await cliente.request(metodo, url, headers=cabeceras)
        if respuesta.status_code in (401, 403):
            negadas[nombre] = respuesta.status_code

    assert negadas == {}
