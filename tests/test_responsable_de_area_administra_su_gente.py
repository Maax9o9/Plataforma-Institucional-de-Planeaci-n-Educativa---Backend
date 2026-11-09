from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.institutional_catalogs.domain.entities import Area

API = "/api/v1"


async def _area(app, codigo: str, nombre: str) -> Area:
    area = Area.create(code=codigo, name=nombre)
    await app.state.area_repository.add(area)
    return area


async def _cuenta(app, client, correo: str, roles: set[Role], area_id: int | None) -> dict:
    usuario = await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name=f"Cuenta {correo}",
            password="password-seguro",
            roles=roles,
            area_id=area_id,
        )
    )
    login = await client.post(
        f"{API}/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {
        "id": usuario.id,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


@pytest.fixture
async def escenario(backend_client):
    app, client = backend_client
    marca = uuid4().hex[:8]
    biomedica = await _area(app, f"DIR-9{marca[:4]}", f"Biomédica {marca}")
    finanzas = await _area(app, f"DIR-8{marca[:4]}", f"Finanzas {marca}")
    jefa = await _cuenta(
        app, client, f"jefa-{marca}@upchiapas.edu.mx", {Role.RESPONSABLE_AREA}, biomedica.id
    )
    ajena = await _cuenta(
        app, client, f"ajena-{marca}@upchiapas.edu.mx", {Role.CAPTURISTA_POA}, finanzas.id
    )
    propia = await _cuenta(
        app, client, f"propia-{marca}@upchiapas.edu.mx", {Role.CAPTURISTA_POA}, biomedica.id
    )
    return {
        "app": app,
        "client": client,
        "biomedica": biomedica,
        "finanzas": finanzas,
        "jefa": jefa,
        "ajena": ajena,
        "propia": propia,
        "marca": marca,
    }


async def test_da_de_alta_a_un_capturista_de_su_area(escenario):
    alta = await escenario["client"].post(
        f"{API}/usuarios",
        headers=escenario["jefa"]["headers"],
        json={
            "correo": f"nueva-{escenario['marca']}@upchiapas.edu.mx",
            "nombre": "Nueva capturista",
            "roles": ["capturista_poa"],
            "area_id": escenario["biomedica"].id,
        },
    )

    assert alta.status_code == 201, alta.text
    assert alta.json()["area_id"] == escenario["biomedica"].id
    assert alta.json()["roles"] == ["capturista_poa"]


async def test_no_da_de_alta_en_otra_area(escenario):
    alta = await escenario["client"].post(
        f"{API}/usuarios",
        headers=escenario["jefa"]["headers"],
        json={
            "correo": f"otra-{escenario['marca']}@upchiapas.edu.mx",
            "nombre": "En otra área",
            "roles": ["capturista_poa"],
            "area_id": escenario["finanzas"].id,
        },
    )

    assert alta.status_code == 403, alta.text
    assert "su área" in alta.json()["message"]


@pytest.mark.parametrize(
    "rol", ["planeacion", "admin_sistema", "rectoria", "revisor_poa", "responsable_area"]
)
async def test_no_otorga_funciones_que_no_son_de_su_area(escenario, rol):
    alta = await escenario["client"].post(
        f"{API}/usuarios",
        headers=escenario["jefa"]["headers"],
        json={
            "correo": f"escalada-{rol}-{escenario['marca']}@upchiapas.edu.mx",
            "nombre": "Intento de escalada",
            "roles": [rol],
            "area_id": escenario["biomedica"].id,
        },
    )

    assert alta.status_code == 403, alta.text


async def test_edita_a_alguien_de_su_area(escenario):
    editado = await escenario["client"].patch(
        f"{API}/usuarios/{escenario['propia']['id']}",
        headers=escenario["jefa"]["headers"],
        json={"nombre": "Nombre corregido"},
    )

    assert editado.status_code == 200, editado.text
    assert editado.json()["nombre"] == "Nombre corregido"


async def test_no_edita_a_alguien_de_otra_area(escenario):
    editado = await escenario["client"].patch(
        f"{API}/usuarios/{escenario['ajena']['id']}",
        headers=escenario["jefa"]["headers"],
        json={"nombre": "Nombre corregido"},
    )

    assert editado.status_code == 403, editado.text


async def test_no_se_lleva_a_su_area_a_alguien_de_otra(escenario):
    editado = await escenario["client"].patch(
        f"{API}/usuarios/{escenario['ajena']['id']}",
        headers=escenario["jefa"]["headers"],
        json={"area_id": escenario["biomedica"].id},
    )

    assert editado.status_code == 403, editado.text


async def test_no_manda_a_los_suyos_a_otra_area(escenario):
    editado = await escenario["client"].patch(
        f"{API}/usuarios/{escenario['propia']['id']}",
        headers=escenario["jefa"]["headers"],
        json={"area_id": escenario["finanzas"].id},
    )

    assert editado.status_code == 403, editado.text


async def test_da_de_baja_a_alguien_de_su_area(escenario):
    baja = await escenario["client"].post(
        f"{API}/usuarios/{escenario['propia']['id']}/desactivar",
        headers=escenario["jefa"]["headers"],
    )

    assert baja.status_code == 200, baja.text
    assert baja.json()["activo"] is False


async def test_no_da_de_baja_a_alguien_de_otra_area(escenario):
    baja = await escenario["client"].post(
        f"{API}/usuarios/{escenario['ajena']['id']}/desactivar",
        headers=escenario["jefa"]["headers"],
    )

    assert baja.status_code == 403, baja.text


async def test_el_listado_solo_le_enseña_a_su_propia_gente(escenario):
    listado = await escenario["client"].get(
        f"{API}/usuarios?limit=100", headers=escenario["jefa"]["headers"]
    )

    assert listado.status_code == 200, listado.text
    areas = {item["area_id"] for item in listado.json()["items"]}
    assert areas == {escenario["biomedica"].id}


async def test_el_listado_no_se_abre_pidiendo_otra_area(escenario):
    listado = await escenario["client"].get(
        f"{API}/usuarios?limit=100&area_id={escenario['finanzas'].id}",
        headers=escenario["jefa"]["headers"],
    )

    assert listado.status_code == 200, listado.text
    areas = {item["area_id"] for item in listado.json()["items"]}
    assert areas == {escenario["biomedica"].id}


async def test_un_responsable_sin_area_no_administra_a_nadie(backend_client):
    app, client = backend_client
    marca = uuid4().hex[:8]
    suelta = await _cuenta(
        app, client, f"sin-area-{marca}@upchiapas.edu.mx", {Role.RESPONSABLE_AREA}, None
    )

    listado = await client.get(f"{API}/usuarios", headers=suelta["headers"])
    alta = await client.post(
        f"{API}/usuarios",
        headers=suelta["headers"],
        json={
            "correo": f"da-igual-{marca}@upchiapas.edu.mx",
            "nombre": "Da igual",
            "roles": ["capturista_poa"],
        },
    )

    assert listado.status_code == 403, listado.text
    assert alta.status_code == 403, alta.text


async def test_planeacion_sigue_viendo_todas_las_areas(escenario):
    de_planeacion = await _cuenta(
        escenario["app"],
        escenario["client"],
        f"planeacion-{escenario['marca']}@upchiapas.edu.mx",
        {Role.PLANEACION},
        None,
    )

    de_finanzas = await escenario["client"].get(
        f"{API}/usuarios?area_id={escenario['finanzas'].id}", headers=de_planeacion["headers"]
    )
    de_biomedica = await escenario["client"].get(
        f"{API}/usuarios?area_id={escenario['biomedica'].id}", headers=de_planeacion["headers"]
    )

    assert {item["area_id"] for item in de_finanzas.json()["items"]} == {
        escenario["finanzas"].id
    }
    assert {item["area_id"] for item in de_biomedica.json()["items"]} == {
        escenario["biomedica"].id
    }


async def test_no_da_de_alta_a_quien_el_directorio_manda_a_otra_area(escenario):
    alta = await escenario["client"].post(
        f"{API}/usuarios",
        headers=escenario["jefa"]["headers"],
        json={
            "correo": "vinculacion@upchiapas.edu.mx",
            "nombre": "Cuenta de Vinculación",
            "roles": ["capturista_poa"],
            "area_id": escenario["biomedica"].id,
        },
    )

    assert alta.status_code == 403, alta.text
    assert "su área" in alta.json()["message"]


@pytest.mark.parametrize("rol", [Role.CAPTURISTA_POA, Role.CONSULTA, Role.REVISOR_POA])
async def test_quien_no_es_responsable_de_area_no_administra_a_nadie(rol):
    from app.modules.identity_access.application.access_control import ensure_can_manage_user
    from app.modules.identity_access.domain.entities import User
    from app.modules.identity_access.infrastructure.repository import InMemoryUserRepository
    from app.shared.domain.exceptions import ForbiddenError

    repositorio = InMemoryUserRepository()
    actor = User.register(
        email=f"sin-mando-{rol.value}@upchiapas.edu.mx",
        full_name="Sin mando",
        password_hash="x",
        roles={rol},
        area_id=4,
    )
    await repositorio.add(actor)

    with pytest.raises(ForbiddenError):
        await ensure_can_manage_user(
            repositorio,
            actor.id,
            assigned_roles={Role.CAPTURISTA_POA},
            area_id=4,
        )
