from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


async def seed_admin(app):
    return await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="planeacion@upchiapas.edu.mx",
            full_name="Planeacion",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA, Role.PLANEACION},
            area_id=None,
        )
    )


@pytest.mark.asyncio
async def test_indicator_capture_validation_scoring_and_report_flow(client, app, tmp_path):
    await seed_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "planeacion@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="consulta-archivo@upchiapas.edu.mx",
            full_name="Consulta archivo",
            password="password-seguro",
            roles={Role.CONSULTA},
            area_id=None,
        )
    )
    consultation_login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "consulta-archivo@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    consultation_headers = {
        "Authorization": f"Bearer {consultation_login.json()['access_token']}"
    }

    area = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "DIP", "nombre": "Direccion de Planeacion"},
        headers=headers,
    )
    area_id = area.json()["id"]
    instrument = await client.post(
        "/api/v1/catalogos/instrumentos",
        json={
            "codigo": "PIDE",
            "nombre": "Programa Institucional",
            "descripcion": "Instrumento institucional",
        },
        headers=headers,
    )
    instrument_id = instrument.json()["id"]
    period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "indicadores",
            "periodicidad": "mensual",
            "anio": 2028,
            "etiqueta": "Ene-2028",
            "fecha_inicio": "2028-01-01",
            "fecha_limite": "2028-01-31",
        },
        headers=headers,
    )
    period_id = period.json()["id"]

    indicator = await client.post(
        "/api/v1/indicadores",
        json={
            "clave": "IND-01",
            "nombre": "Cobertura educativa",
            "metodo_calculo": "Resultado / meta * 100",
            "unidad_medida": "Porcentaje",
            "area_id": area_id,
            "responsable_id": (await client.get("/api/v1/auth/me", headers=headers)).json()["id"],
            "periodicidad": "mensual",
            "instrumento_ids": [instrument_id],
        },
        headers=headers,
    )
    assert indicator.status_code == 201, indicator.text
    indicator_id = indicator.json()["id"]
    goal = await client.post(
        f"/api/v1/indicadores/{indicator_id}/metas",
        json={"periodo_id": period_id, "valor": "100"},
        headers=headers,
    )
    assert goal.status_code == 201, goal.text
    opened = await client.post(f"/api/v1/periodos/{period_id}/abrir", headers=headers)
    assert opened.status_code == 200, opened.text

    capture = await client.post(
        "/api/v1/capturas",
        json={"indicador_id": indicator_id, "periodo_id": period_id, "resultado": "100"},
        headers=headers,
    )
    assert capture.status_code == 201, capture.text
    capture_id = capture.json()["id"]
    app.state.settings.upload_directory = str(tmp_path)
    upload = await client.post(
        "/api/v1/archivos",
        files={"archivo": ("reporte.pdf", b"%PDF-1.4\nsecure", "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    uploaded = upload.json()
    file_evidence = await client.post(
        "/api/v1/evidencias",
        json={
            "nombre": "Reporte seguro",
            "descripcion": "Archivo de evidencia",
            "fecha": "2028-01-31",
            "tipo": "archivo",
            "ruta_o_url": uploaded["ruta"],
            "entidad": "captura",
            "entidad_id": capture_id,
            "mime_type": uploaded["mime_type"],
            "tamanio_bytes": uploaded["tamanio_bytes"],
            "checksum_sha256": uploaded["checksum_sha256"],
        },
        headers=headers,
    )
    assert file_evidence.status_code == 201, file_evidence.text
    download_path = file_evidence.json()["version_actual"]["ruta_o_url"]
    download = await client.get(download_path, headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
    assert (
        await client.get(download_path, headers=consultation_headers)
    ).status_code == 403
    evidence = await client.post(
        "/api/v1/evidencias",
        json={
            "nombre": "Reporte mensual",
            "descripcion": "Evidencia de prueba",
            "fecha": "2028-01-31",
            "tipo": "enlace",
            "ruta_o_url": "https://example.com/evidencia",
            "entidad": "captura",
            "entidad_id": capture_id,
        },
        headers=headers,
    )
    assert evidence.status_code == 201, evidence.text
    sent = await client.post(f"/api/v1/capturas/{capture_id}/enviar", headers=headers)
    assert sent.status_code == 200, sent.text
    validated = await client.post(f"/api/v1/capturas/{capture_id}/validar", headers=headers)
    assert validated.status_code == 200, validated.text
    assert validated.json()["semaforo"] == "verde"
    assert float(validated.json()["porcentaje_avance"]) == 100
    notifications = await client.get("/api/v1/notificaciones", headers=headers)
    assert notifications.status_code == 200
    assert any(item["tipo"] == "validacion" for item in notifications.json())

    history = await client.get(f"/api/v1/capturas/{capture_id}/historial", headers=headers)
    assert history.status_code == 200
    assert [item["a_estado"] for item in history.json()["items"]] == [
        "validado",
        "enviado",
        "borrador",
    ]

    trend = await client.get(f"/api/v1/indicadores/{indicator_id}/tendencia", headers=headers)
    assert trend.status_code == 200
    assert trend.json()[0]["semaforo"] == "verde"
    report = await client.get("/api/v1/reportes/institucional", headers=headers)
    assert report.status_code == 200
    assert report.json()["tipo"] == "institucional"
    xlsx = await client.get(
        "/api/v1/reportes/institucional?formato=xlsx",
        headers=headers,
    )
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    pdf = await client.get(
        "/api/v1/reportes/institucional?formato=pdf",
        headers=headers,
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
