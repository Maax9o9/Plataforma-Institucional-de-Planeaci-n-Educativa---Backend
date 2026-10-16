"""El catalogo del PSE se administra, y darlo de baja no borra lo ya formulado.

La regla que gobierna este modulo: `activo` decide lo que se puede *elegir de
nuevo*, no lo que ya se eligio. Una cedula apunta al catalogo por llave
foranea, asi que retirar una estrategia tiene que dejar intacta la cedula donde
se uso -con su denominacion y todo-, y a la vez impedir que alguien la vuelva a
elegir. Por eso no hay borrado: borrar si romperia el POA ya verificado.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.application.use_cases.manage_catalog import PoaCatalogAdmin
from app.modules.poa_planning.infrastructure.cedula_repository import (
    InMemoryPoaFormRepository,
)
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError
from helpers import cuatrimestres, poa_inicial_id

CATALOGO = "/api/v1/poa/catalogos"


def _poa(catalogo_id: int, ruta: str) -> str:
    """La URL de un elemento del catálogo dentro de su POA, que es obligatorio."""
    separador = "&" if "?" in ruta else "?"
    return f"{CATALOGO}/{ruta}{separador}catalogo_id={catalogo_id}"


async def _account(app, client, role: Role, suffix: str, area_id: int | None = None):
    email = f"catalogo-pse-{role.value}-{suffix}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name=f"Catalogo PSE {role.value}",
            password="password-seguro",
            roles={role},
            area_id=area_id,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": email, "contrasena": "password-seguro"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _nueva_rama(client, headers) -> dict[str, str | int]:
    """Da de alta un objetivo propio con su estrategia, indicador y accion.

    Se usa un numero de objetivo libre en vez de tocar el PSE cargado: asi la
    prueba puede deshabilitar lo que acaba de crear sin dejar inservible el
    catalogo real para las demas pruebas de la misma base.
    """
    catalogo_id = await poa_inicial_id(client, headers)
    objetivos = await client.get(_poa(catalogo_id, "objetivos?solo_activos=false"), headers=headers)
    assert objetivos.status_code == 200, objetivos.text
    numero = max((item["numero"] for item in objetivos.json()), default=0) + 1
    estrategia = f"{numero}.1"
    indicador = f"{numero}.1"
    accion = f"{numero}.1.1"

    creado = await client.post(
        _poa(catalogo_id, f"objetivos/{numero}"),
        headers=headers,
        json={"clave": f"OBJ-{numero}", "denominacion": f"Objetivo de prueba {numero}"},
    )
    assert creado.status_code == 201, creado.text
    assert creado.json() == {
        "clave": f"OBJ-{numero}",
        "numero": numero,
        "denominacion": f"Objetivo de prueba {numero}",
        "activo": True,
    }

    for ruta, cuerpo in (
        (
            f"estrategias/{estrategia}",
            {"objetivo_numero": numero, "denominacion": f"Estrategia de prueba {estrategia}"},
        ),
        (
            f"indicadores/{indicador}",
            {
                "objetivo_numero": numero,
                "nombre": f"Indicador de prueba {indicador}",
                "formula": "(a / b) * 100",
                "unidad_medida": "Porcentaje",
            },
        ),
        (
            f"actividades/{accion}",
            {"estrategia_clave": estrategia, "descripcion": f"Accion de prueba {accion}"},
        ),
    ):
        respuesta = await client.post(_poa(catalogo_id, ruta), headers=headers, json=cuerpo)
        assert respuesta.status_code == 201, respuesta.text

    return {
        "catalogo_id": catalogo_id,
        "objetivo": numero,
        "estrategia": estrategia,
        "indicador": indicador,
        "accion": accion,
    }


async def _deshabilitar(client, headers, rama) -> None:
    peticiones = (
        (
            f"estrategias/{rama['estrategia']}",
            {
                "objetivo_numero": rama["objetivo"],
                "denominacion": f"Estrategia de prueba {rama['estrategia']}",
                "activo": False,
            },
        ),
        (
            f"indicadores/{rama['indicador']}",
            {
                "objetivo_numero": rama["objetivo"],
                "nombre": f"Indicador de prueba {rama['indicador']}",
                "formula": "(a / b) * 100",
                "unidad_medida": "Porcentaje",
                "activo": False,
            },
        ),
        (
            f"actividades/{rama['accion']}",
            {
                "estrategia_clave": rama["estrategia"],
                "descripcion": f"Accion de prueba {rama['accion']}",
                "activo": False,
            },
        ),
    )
    for ruta, cuerpo in peticiones:
        respuesta = await client.patch(
            _poa(rama["catalogo_id"], ruta), headers=headers, json=cuerpo
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["activo"] is False


async def _cedula_con_la_rama(client, headers, rama, area_id: int) -> dict:
    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            "/api/v1/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
        if ejercicio.status_code == 201:
            break
        assert ejercicio.status_code == 409, ejercicio.text
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontro un anio libre para el ejercicio POA de prueba.")

    cedula = await client.post(
        "/api/v1/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": ejercicio.json()["id"],
            "estrategia_clave": rama["estrategia"],
            "area_responsable_id": area_id,
            "cuatrimestres": cuatrimestres(anio),
        },
    )
    assert cedula.status_code == 201, cedula.text
    cedula_id = cedula.json()["id"]

    indicador = await client.post(
        f"/api/v1/poa/cedulas/{cedula_id}/indicadores",
        headers=headers,
        json={"indicador_clave": rama["indicador"], "meta_institucional": "80"},
    )
    assert indicador.status_code == 201, indicador.text

    actividad = await client.post(
        f"/api/v1/poa/cedulas/{cedula_id}/actividades",
        headers=headers,
        json={
            "actividad_clave": rama["accion"],
            "unidad_medida": "Informe",
            "meta_anual": "3",
            "area_ejecutora_id": area_id,
        },
    )
    assert actividad.status_code == 201, actividad.text

    # Sin seguimiento no hay tarjeta en el tablero: la programacion del primer
    # cuatrimestre es lo que lo hace aparecer.
    periodo_id = next(c["periodo_id"] for c in cedula.json()["cuatrimestres"] if c["numero"] == 1)
    abierto = await client.post(f"/api/v1/periodos/{periodo_id}/abrir", headers=headers)
    assert abierto.status_code == 200, abierto.text
    seguimiento = await client.put(
        f"/api/v1/poa/cedulas/actividades/{actividad.json()['id']}/seguimientos/1",
        headers=headers,
        json={"periodo_id": periodo_id, "programado": "1"},
    )
    assert seguimiento.status_code in (200, 201), seguimiento.text
    return {"id": cedula_id, "ejercicio_id": ejercicio.json()["id"], "anio": anio}


async def _area(client, headers, suffix: str) -> int:
    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={"codigo": f"CAT-{suffix}", "nombre": f"Area catalogo PSE {suffix}"},
    )
    assert area.status_code == 201, area.text
    return area.json()["id"]


@pytest.mark.asyncio
async def test_la_baja_del_catalogo_no_toca_la_cedula_ya_formulada(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    area_id = await _area(client, headers, suffix)
    rama = await _nueva_rama(client, headers)
    cedula = await _cedula_con_la_rama(client, headers, rama, area_id)

    await _deshabilitar(client, headers, rama)

    # Lo que ya se formulo sigue completo, con denominacion y todo: es la razon
    # de que exista `activo` en vez de un DELETE.
    detalle = await client.get(f"/api/v1/poa/cedulas/{cedula['id']}", headers=headers)
    assert detalle.status_code == 200, detalle.text
    cuerpo = detalle.json()
    assert cuerpo["estrategia_clave"] == rama["estrategia"]
    assert cuerpo["estrategia_denominacion"] == f"Estrategia de prueba {rama['estrategia']}"
    assert cuerpo["objetivo_denominacion"] == f"Objetivo de prueba {rama['objetivo']}"
    assert [item["nombre"] for item in cuerpo["indicadores"]] == [
        f"Indicador de prueba {rama['indicador']}"
    ]
    assert [item["descripcion"] for item in cuerpo["actividades"]] == [
        f"Accion de prueba {rama['accion']}"
    ]

    # Y el tablero tambien resuelve la descripcion de una accion retirada.
    tablero = await client.get(
        f"/api/v1/poa/seguimientos?ejercicio_id={cedula['ejercicio_id']}&cuatrimestre=1",
        headers=headers,
    )
    assert tablero.status_code == 200, tablero.text
    tarjetas = tablero.json()["items"]
    assert [t["actividad"]["descripcion"] for t in tarjetas] == [
        f"Accion de prueba {rama['accion']}"
    ]


@pytest.mark.asyncio
async def test_lo_deshabilitado_ya_no_se_puede_elegir(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    area_id = await _area(client, headers, suffix)
    rama = await _nueva_rama(client, headers)
    cedula = await _cedula_con_la_rama(client, headers, rama, area_id)
    await _deshabilitar(client, headers, rama)

    # El selector deja de ofrecerlo...
    for ruta, clave in (
        (f"estrategias?objetivo_numero={rama['objetivo']}", rama["estrategia"]),
        (f"indicadores?objetivo_numero={rama['objetivo']}", rama["indicador"]),
        (f"actividades?estrategia_clave={rama['estrategia']}", rama["accion"]),
    ):
        vigentes = await client.get(_poa(rama["catalogo_id"], ruta), headers=headers)
        assert vigentes.status_code == 200, vigentes.text
        assert clave not in [item["clave"] for item in vigentes.json()]

        separador = "&" if "?" in ruta else "?"
        todo = await client.get(
            _poa(rama["catalogo_id"], f"{ruta}{separador}solo_activos=false"), headers=headers
        )
        assert todo.status_code == 200, todo.text
        retirado = next(item for item in todo.json() if item["clave"] == clave)
        assert retirado["activo"] is False

    # ...y el backend lo rechaza aunque alguien lo mande a mano.
    otra = await client.post(
        "/api/v1/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": cedula["ejercicio_id"],
            "estrategia_clave": rama["estrategia"],
            "area_responsable_id": area_id,
            "cuatrimestres": cuatrimestres(cedula["anio"]),
        },
    )
    assert otra.status_code == 404, otra.text

    indicador = await client.post(
        f"/api/v1/poa/cedulas/{cedula['id']}/indicadores",
        headers=headers,
        json={"indicador_clave": rama["indicador"]},
    )
    assert indicador.status_code == 404, indicador.text

    actividad = await client.post(
        f"/api/v1/poa/cedulas/{cedula['id']}/actividades",
        headers=headers,
        json={
            "actividad_clave": rama["accion"],
            "unidad_medida": "Informe",
            "meta_anual": "1",
        },
    )
    assert actividad.status_code == 404, actividad.text


@pytest.mark.asyncio
async def test_lo_deshabilitado_se_vuelve_a_habilitar(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    rama = await _nueva_rama(client, headers)
    await _deshabilitar(client, headers, rama)

    revivida = await client.patch(
        _poa(rama["catalogo_id"], f"estrategias/{rama['estrategia']}"),
        headers=headers,
        json={
            "objetivo_numero": rama["objetivo"],
            "denominacion": "Estrategia corregida",
            "activo": True,
        },
    )
    assert revivida.status_code == 200, revivida.text
    assert revivida.json()["activo"] is True
    assert revivida.json()["denominacion"] == "Estrategia corregida"

    vigentes = await client.get(
        _poa(rama["catalogo_id"], f"estrategias?objetivo_numero={rama['objetivo']}"),
        headers=headers,
    )
    assert rama["estrategia"] in [item["clave"] for item in vigentes.json()]


@pytest.mark.asyncio
async def test_alta_duplicada_y_edicion_de_lo_inexistente(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    rama = await _nueva_rama(client, headers)

    # Un alta nunca pisa en silencio lo que ya esta capturado.
    duplicado = await client.post(
        _poa(rama["catalogo_id"], f"estrategias/{rama['estrategia']}"),
        headers=headers,
        json={"objetivo_numero": rama["objetivo"], "denominacion": "Otra cosa"},
    )
    assert duplicado.status_code == 409, duplicado.text

    ausente = await client.patch(
        _poa(rama["catalogo_id"], "estrategias/99.9"),
        headers=headers,
        json={"objetivo_numero": rama["objetivo"], "denominacion": "No existe"},
    )
    assert ausente.status_code == 404, ausente.text

    # Y el padre tiene que existir: el error dice cual de los dos datos esta mal.
    huerfana = await client.post(
        _poa(rama["catalogo_id"], f"estrategias/{rama['objetivo']}.9"),
        headers=headers,
        json={"objetivo_numero": 999, "denominacion": "Sin objetivo"},
    )
    assert huerfana.status_code == 422, huerfana.text
    assert "999" in huerfana.json()["message"]


@pytest.mark.asyncio
async def test_solo_planeacion_administra_el_catalogo(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    planeacion = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    rama = await _nueva_rama(client, planeacion)
    area_id = await _area(client, planeacion, suffix)
    capturista = await _account(app, client, Role.CAPTURISTA_POA, suffix, area_id=area_id)

    denegado = await client.patch(
        _poa(rama["catalogo_id"], f"estrategias/{rama['estrategia']}"),
        headers=capturista,
        json={
            "objetivo_numero": rama["objetivo"],
            "denominacion": "Mi version",
            "activo": False,
        },
    )
    assert denegado.status_code == 403, denegado.text

    # Pero si puede consultarlo: formular requiere leer el catalogo.
    lectura = await client.get(_poa(rama["catalogo_id"], "estrategias"), headers=capturista)
    assert lectura.status_code == 200, lectura.text


@pytest.mark.asyncio
async def test_el_caso_de_uso_tambien_exige_planeacion():
    """La segunda cerradura, la que no depende del router.

    `test_solo_planeacion_administra_el_catalogo` comprueba la puerta HTTP, y
    pasaria igual si el caso de uso dejara de validar: el 403 lo devuelve
    `require_roles`. El catalogo del PSE es la definicion del POA de toda la
    universidad, asi que la regla vive tambien adentro -como en la aprobacion
    del ejercicio-, para que un router nuevo no la pueda saltar sin darse
    cuenta.
    """
    admin = PoaCatalogAdmin(InMemoryPoaFormRepository())
    intruso = ActorContext(id=99, roles=frozenset({"capturista_poa"}), area_id=1)

    with pytest.raises(ForbiddenError):
        await admin.save_strategy(
            catalog_id=1,
            key="1.1",
            objective_number=1,
            denomination="Mi version",
            is_active=False,
            actor=intruso,
            creating=False,
        )
