"""La bitácora responde «quién hizo qué con el POA», no quién entró al sistema."""

from __future__ import annotations

import pytest

from test_ep08_revision_poa import _capturar, _escenario


@pytest.mark.asyncio
async def test_la_bitacora_no_guarda_inicios_de_sesion_ni_renovaciones(backend_client):
    """Un inicio de sesión no dice quién capturó, envió o evaluó una actividad,
    y en la práctica los ahogaba: de unos 200 registros, 132 eran `login` y
    `refresh`, así que encontrar una modificación real costaba varias páginas.

    Estos eventos no dejan de importar —los intentos fallidos son lo que delata
    a alguien intentando entrar—, pero su lugar es `bitacora_accesos`, que la
    migración 0002 creó aparte para poder purgarla con otra política sin tocar
    la bitácora inmutable.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)

    # _escenario crea varias cuentas y cada una inicia sesión: si los eventos de
    # sesión siguieran entrando, aquí ya habría varios.
    bitacora = await client.get(
        "/api/v1/bitacora",
        headers=escenario["admin_headers"],
        params={"limit": 100},
    )

    assert bitacora.status_code == 200, bitacora.text
    acciones = {fila["accion"] for fila in bitacora.json()["items"]}
    # password_changed no entra en esta lista a proposito: cambiar una
    # contrasena si debe quedar registrado, y ademas el cambio se revierte si
    # su entrada no se escribe.
    assert acciones.isdisjoint({"login", "logout", "refresh"}), acciones


@pytest.mark.asyncio
async def test_la_bitacora_conserva_el_nombre_de_quien_lo_hizo(backend_client):
    """Si mañana esa persona deja la institución y su cuenta se da de baja, la
    bitácora tiene que seguir diciendo que fue ella: el nombre se copia al
    escribir el registro y no se vuelve a leer del directorio.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)
    await _capturar(client, escenario)

    bitacora = await client.get(
        "/api/v1/bitacora",
        headers=escenario["admin_headers"],
        params={"entidad": "poa_form_follow_up"},
    )

    assert bitacora.status_code == 200, bitacora.text
    filas = bitacora.json()["items"]
    assert filas, "la captura del seguimiento debería haber dejado bitácora"
    assert all(fila["usuario_nombre"] for fila in filas), filas


@pytest.mark.asyncio
async def test_si_deja_bitacora_lo_que_se_hace_sobre_el_poa(backend_client):
    """Lo que sí debe quedar: quién capturó el avance de una actividad."""
    app, client = backend_client
    escenario = await _escenario(app, client)
    await _capturar(client, escenario)

    bitacora = await client.get(
        "/api/v1/bitacora",
        headers=escenario["admin_headers"],
        params={"entidad": "poa_form_follow_up"},
    )

    assert bitacora.status_code == 200, bitacora.text
    assert bitacora.json()["total"] >= 1
