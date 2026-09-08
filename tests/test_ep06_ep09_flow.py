"""El flujo incorrecto no debe volver a exponerse accidentalmente."""

import pytest


def test_openapi_only_exposes_current_poa(app):
    paths = app.openapi()["paths"]
    assert "/api/v1/poa/cedulas" in paths
    assert "/api/v1/poa/ejercicios" in paths
    assert "/api/v1/poa/reportes/por-cedula" in paths
    assert not any(
        path.startswith(
            (
                "/api/v1/poa/procesos",
                "/api/v1/poa/objetivos",
                "/api/v1/poa/actividades",
                "/api/v1/poa/avances",
                "/api/v1/poa/reportes/por-proceso",
            )
        )
        for path in paths
    )
    assert not hasattr(app.state, "poa_advance_repository")


@pytest.mark.asyncio
async def test_legacy_routes_are_not_available(client):
    for route in ("procesos", "objetivos", "actividades", "avances"):
        response = await client.post(f"/api/v1/poa/{route}", json={})
        assert response.status_code == 404
