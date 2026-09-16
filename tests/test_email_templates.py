from __future__ import annotations

import re
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.email_templates.domain.entities import personalize, validate_content
from app.modules.email_templates.infrastructure.rendering import (
    ASSETS,
    TEMPLATE_ROOT,
    FileTemplateCatalog,
    HtmlEmailRenderer,
)
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.shared.domain.exceptions import ValidationError
from app.shared.infrastructure.email.smtp_email_sender import SmtpEmailSender

BASE = "/api/v1/correos/plantillas"


async def account(application, client, role):
    email = f"mail-{uuid4().hex}@example.com"
    user = await CreateUser(
        application.state.user_repository,
        application.state.password_hasher,
        application.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name="María López",
            password="password-seguro",
            roles={role},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login", json={"correo": email, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_templates_edit_preview_conflict_restore_and_persistence(backend_client):
    app, client = backend_client
    user, headers = await account(app, client, Role.ADMIN_SISTEMA)
    response = await client.get(BASE, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 14
    key = "poa_captura_7d"
    existing = (await client.get(f"{BASE}/{key}", headers=headers)).json()
    body = {
        "version": existing["version"],
        "contenido": {
            "asunto": "Hola {{nombre}}, revisa tu POA",
            "cuerpo": "Nuevo texto\n\nSegunda línea.",
        },
    }
    changed = await client.patch(f"{BASE}/{key}", headers=headers, json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json()["personalizada"]
    assert changed.json()["actualizado_por"] == user.id
    assert changed.json()["version"] == existing["version"] + 1
    saved = await app.state.email_template_repository.get(key)
    assert saved.content["cuerpo"] == body["contenido"]["cuerpo"]
    if app.state.db_session_factory:
        from app.modules.email_templates.infrastructure.sql_repository import (
            SqlAlchemyTemplateRepository,
        )

        fresh = SqlAlchemyTemplateRepository(app.state.db_session_factory)
        assert (await fresh.get(key)).version == saved.version
    conflict = await client.patch(f"{BASE}/{key}", headers=headers, json=body)
    assert conflict.status_code == 409
    assert conflict.json()["details"]["reason"] == "EMAIL_TEMPLATE_VERSION_CONFLICT"
    preview = await client.post(
        f"{BASE}/{key}/vista-previa",
        headers=headers,
        json={
            "nombre_destinatario": "Ana <script>alert(1)</script>",
            "contenido": {"cuerpo": "Texto no guardado <img src=x onerror=alert(1)>"},
        },
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["es_vista_previa"] is True
    assert "Ana" in result["asunto"]
    assert "<script>" not in result["html"]
    assert "<img src=x" not in result["html"]
    assert "&lt;script&gt;" in result["html"]
    assert "data:image/png;base64," in result["html"]
    assert "cid:" not in result["html"]
    assert "example.invalid" in result["texto"]
    assert (await app.state.email_template_repository.get(key)).content == saved.content
    reset = await client.post(
        f"{BASE}/{key}/restaurar", headers=headers, json={"version": changed.json()["version"]}
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["personalizada"] is False
    assert reset.json()["contenido"] == reset.json()["predeterminado"]
    assert reset.json()["version"] == existing["version"] + 2
    assert (await client.get(f"{BASE}/no-existe", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_template_administration_requires_admin(client, app):
    assert (await client.get(BASE)).status_code == 401
    for role in (Role.CAPTURISTA_POA, Role.PLANEACION, Role.CONSULTA):
        _, headers = await account(app, client, role)
        for method, url, body in (
            ("GET", BASE, None),
            ("PATCH", f"{BASE}/invitacion", {"version": 0, "contenido": {"titulo": "X"}}),
            ("POST", f"{BASE}/invitacion/restaurar", {"version": 0}),
            ("POST", f"{BASE}/invitacion/vista-previa", {}),
        ):
            result = await client.request(method, url, headers=headers, json=body)
            assert result.status_code == 403, result.text
    _, headers = await account(app, client, Role.PLANEACION_ADMIN)
    assert (await client.get(BASE, headers=headers)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"cuerpo": " "},
        {"cuerpo": None},
        {"cuerpo": "{{token}}"},
        {"asunto": "Asunto\r\nBcc: extra@example.com"},
        {"titulo": "a\nb"},
        {"html": "<b>No</b>"},
        {},
        {"cuerpo": "a" * 6001},
    ],
)
async def test_invalid_custom_content_rejected_without_saving(client, app, changes):
    _, headers = await account(app, client, Role.ADMIN_SISTEMA)
    result = await client.patch(
        f"{BASE}/invitacion",
        headers=headers,
        json={
            "version": 0,
            "contenido": changes,
        },
    )
    assert result.status_code == 422, result.text
    assert await app.state.email_template_repository.get("invitacion") is None


@pytest.mark.asyncio
async def test_custom_invitation_keeps_real_single_use_link(client, app):
    _, headers = await account(app, client, Role.ADMIN_SISTEMA)
    sender = AsyncMock()
    app.state.email_sender = sender
    result = await client.patch(
        f"{BASE}/invitacion",
        headers=headers,
        json={
            "version": 0,
            "contenido": {"asunto": "Bienvenida, {{nombre}}", "cuerpo": "Texto del administrador."},
        },
    )
    assert result.status_code == 200
    created = await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json={
            "correo": f"invite-{uuid4().hex}@example.com",
            "nombre": "Ana <b>López</b>",
            "roles": ["consulta"],
        },
    )
    assert created.status_code == 201, created.text
    args = sender.send.call_args.args
    assert args[1] == "Bienvenida, Ana <b>López</b>"
    assert "Ana &lt;b&gt;López&lt;/b&gt;" in args[2]
    assert "Texto del administrador." in args[2]
    assert "24 horas" in args[3]
    token = re.search(r"[?]token=([A-Za-z0-9_-]+)", args[3]).group(1)
    configured = await client.post(
        "/api/v1/auth/password-setup",
        json={
            "token": token,
            "contrasena": "Mi-contrasena-segura",
        },
    )
    assert configured.status_code == 204
    reused = await client.post(
        "/api/v1/auth/password-setup",
        json={
            "token": token,
            "contrasena": "Otra-contrasena-segura",
        },
    )
    assert reused.status_code == 401


@pytest.mark.parametrize("definition", FileTemplateCatalog().list(), ids=lambda d: d.key)
def test_all_templates_render_secure_multipart_content(definition):
    result = HtmlEmailRenderer().render(
        definition,
        definition.content,
        recipient_name="Ana <img src=x>",
        detail="Pendiente <dato> & evidencia",
        action_url="https://example.com/?a=1&b=2",
    )
    assert "Ana &lt;img src=x&gt;" in result.html
    assert "Pendiente &lt;dato&gt; &amp; evidencia" in result.html
    assert "https://example.com/?a=1&amp;b=2" in result.html
    assert 'name="viewport"' in result.html
    assert "@media screen" in result.html
    assert "height:600px" not in result.html
    assert "data:image" not in result.html
    assert "cid:upchiapas-horizontal" in result.html
    assert len(result.html.encode()) < 100_000
    assert "{{nombre}}" not in result.text


@pytest.mark.asyncio
async def test_smtp_has_related_images_and_plain_text(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr("aiosmtplib.send", send)
    sender = SmtpEmailSender(
        host="smtp.example.com",
        port=587,
        username="test",
        password="test",
        sender="test@example.com",
        inline_assets={cid: TEMPLATE_ROOT / "assets" / name for cid, name in ASSETS.items()},
    )
    definition = FileTemplateCatalog().get("invitacion")
    email = HtmlEmailRenderer().render(
        definition,
        definition.content,
        recipient_name="Ana",
        detail="Vigencia: 24 horas",
        action_url="https://example.com/?token=solo-prueba",
    )
    await sender.send("ana@example.com", email.subject, email.html, email.text)
    message = send.call_args.args[0]
    assert message.get_content_type() == "multipart/alternative"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == email.text
    html_part = message.get_body(preferencelist=("html",))
    assert "Hola Ana" in html_part.get_content()
    images = [part for part in message.walk() if part.get_content_maintype() == "image"]
    assert {part["Content-ID"] for part in images} == {f"<{cid}>" for cid in ASSETS}
    assert all(part.get_content_disposition() == "inline" for part in images)
    assert send.call_args.kwargs["start_tls"] is True


def test_no_template_evaluation_or_header_injection():
    assert personalize("Hola {{nombre}}", "Ana\r\nBcc: other@example.com") == (
        "Hola Ana  Bcc: other@example.com"
    )
    with pytest.raises(ValidationError):
        validate_content({"cuerpo": "{{nombre.__class__}}"})
    definition = FileTemplateCatalog().get("invitacion")
    with pytest.raises(ValidationError):
        HtmlEmailRenderer().render(
            definition,
            definition.content,
            recipient_name="Ana",
            detail="Mensaje",
            action_url="javascript:alert(1)",
        )
