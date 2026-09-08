from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.core.validation_messages import validation_detail
from app.modules.periods.domain.value_objects import PeriodStatus
from app.modules.poa_planning.application.completeness import emission_errors
from app.modules.poa_planning.application.use_cases.manage_cedula import _validate_period
from app.shared.domain.exceptions import InvalidStateError, ValidationError


@pytest.mark.asyncio
async def test_emission_returns_all_pending_fields():
    detail = SimpleNamespace(
        form=SimpleNamespace(strategy_type=None, signatories=()),
        activities=[SimpleNamespace(id=10), SimpleNamespace(id=11)],
        indicators=[SimpleNamespace(id=20, total_achieved=None, achieved_percentage=None)],
        follow_ups=[
            SimpleNamespace(
                id=30, form_activity_id=10, quarter=3, achieved=None, progress=" ", scope=None
            )
        ],
    )
    evidences = AsyncMock()
    evidences.list_for.return_value = []
    errors = await emission_errors(detail, 3, evidences)
    assert {e["field"] for e in errors} == {
        "tipo_estrategia",
        "firmantes",
        "alcanzado",
        "progreso",
        "alcance",
        "evidencias",
        "seguimiento",
        "total_alcanzado",
        "porcentaje_alcanzado",
    }
    assert next(e for e in errors if e["field"] == "evidencias")["actividad_id"] == 10
    assert next(e for e in errors if e["field"] == "total_alcanzado")["indicador_id"] == 20


@pytest.mark.asyncio
async def test_period_errors_have_stable_reasons():
    forms, periods, exercises = AsyncMock(), AsyncMock(), AsyncMock()
    forms.list_form_quarters.return_value = [SimpleNamespace(quarter=3, period_id=103)]
    args = dict(
        repository=forms,
        periods=periods,
        exercises=exercises,
        form=SimpleNamespace(id=1),
        quarter=3,
    )
    with pytest.raises(ValidationError) as mismatch:
        await _validate_period(**args, period_id=101)
    assert mismatch.value.details["reason"] == "POA_PERIOD_MISMATCH"
    assert mismatch.value.details["periodo_esperado_id"] == 103
    periods.get_by_id.return_value = SimpleNamespace(id=103, status=PeriodStatus.CLOSED)
    with pytest.raises(InvalidStateError) as closed:
        await _validate_period(**args, period_id=103)
    assert closed.value.details["reason"] == "POA_PERIOD_NOT_OPEN"


@pytest.mark.asyncio
async def test_structured_errors_do_not_expose_secrets_and_keep_request_id(app):
    from app.modules.poa_planning.api.cedula_schemas import CapturarTotalIndicadorRequest

    @app.post("/_test/validate")
    async def validate(body: CapturarTotalIndicadorRequest):
        return body

    @app.get("/_test/unavailable")
    async def unavailable():
        raise OperationalError("SELECT private_data", {}, RuntimeError("secret-db-password"))

    @app.get("/_test/error")
    async def broken():
        raise RuntimeError("secret-internal-path")

    @app.get("/_test/business")
    async def business():
        raise ValidationError("Revise los datos.", details={"fecha": date(2036, 9, 1)})

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/_test/validate",
            json={
                "periodo_id": 103,
                "total_alcanzado": 0,
                "contrasena": "sensitive-value",
            },
        )
        assert response.status_code == 422
        errors = {e["field"]: e for e in response.json()["details"]}
        assert errors["porcentaje_alcanzado"]["msg"] == "Este campo es obligatorio."
        assert errors["contrasena"]["type"] == "extra_forbidden"
        assert "sensitive-value" not in response.text
        for route, status, code in (
            ("unavailable", 503, "SERVICE_UNAVAILABLE"),
            ("error", 500, "INTERNAL_SERVER_ERROR"),
        ):
            result = await client.get(f"/_test/{route}", headers={"X-Request-ID": "poa-test-id"})
            assert result.status_code == status
            assert result.json()["code"] == code
            assert result.json()["request_id"] == result.headers["x-request-id"] == "poa-test-id"
            assert "secret-" not in result.text and "SELECT" not in result.text
        assert (await client.get("/_test/unavailable")).headers["retry-after"] == "5"
        result = await client.get("/_test/business")
        assert result.status_code == 422
        assert result.json()["details"]["fecha"] == "2036-09-01"


def test_nested_validation_locations_are_mappable_to_form_fields():
    result = validation_detail(
        {
            "loc": ("body", "firmantes", 1, "nombre"),
            "msg": "Field required",
            "type": "missing",
            "input": "secret",
        }
    )
    assert result["field"] == "firmantes.1.nombre"
    assert "input" not in result
