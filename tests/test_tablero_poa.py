"""Tablero del POA: criterio SEAES en la actividad y listado de seguimientos."""

from __future__ import annotations

import pytest

from test_ep08_revision_poa import _escenario


@pytest.mark.asyncio
async def test_el_area_asigna_el_criterio_seaes_de_su_actividad(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    criterio = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"clave": f"C-{escenario['anio']}", "nombre": "Pertinencia de los programas"},
    )
    assert criterio.status_code == 201, criterio.text
    criterio_id = criterio.json()["id"]

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterio-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_id": criterio_id},
    )

    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_id"] == criterio_id


@pytest.mark.asyncio
async def test_el_criterio_debe_existir(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    fallido = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterio-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_id": 999999},
    )

    assert fallido.status_code == 404, fallido.text
