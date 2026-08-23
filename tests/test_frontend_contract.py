from __future__ import annotations

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


async def _authenticate_admin(client, app) -> dict[str, str]:
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="contract-admin@upchiapas.edu.mx",
            full_name="Administrador de contrato",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "contract-admin@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_openapi_describes_frontend_contract(app):
    schema = app.openapi()

    assert schema["info"]["version"] == "0.2.0"
    assert schema["paths"]["/health/live"]["get"]["security"] == []
    assert schema["paths"]["/health/ready"]["get"]["security"] == []
    assert schema["paths"]["/api/v1/auth/refresh"]["post"]["security"] == [
        {"refreshCookie": []}
    ]
    assert schema["paths"]["/api/v1/auth/logout"]["post"]["security"] == [
        {"bearerAuth": []}
    ]
    assert schema["paths"]["/api/v1/auditoria"]["get"]["deprecated"] is True

    validation = schema["paths"]["/api/v1/indicadores"]["get"]["responses"]["422"]
    assert validation["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    report_content = schema["paths"]["/api/v1/reportes/institucional"]["get"][
        "responses"
    ]["200"]["content"]
    assert "application/json" in report_content
    assert "application/pdf" in report_content
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in report_content
    )


async def test_health_checks_are_public_and_distinguish_liveness(client):
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "environment": "testing"}
    assert ready.status_code == 200
    assert ready.json()["database"] == "in_memory"


async def test_unknown_indicator_sort_uses_normalized_422(client, app):
    headers = await _authenticate_admin(client, app)
    response = await client.get(
        "/api/v1/indicadores?sort=campo_inexistente",
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["request_id"]
