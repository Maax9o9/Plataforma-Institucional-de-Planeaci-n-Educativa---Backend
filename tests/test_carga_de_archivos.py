"""Qué archivos acepta la carga de evidencias, y por qué.

La comprobación es por el contenido y no por el nombre: la extensión la elige
quien sube, así que un `.xlsm` renombrado a `.docx` pasaría cualquier filtro
que mirara el nombre.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def _headers(client, app) -> dict[str, str]:
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="carga-archivos@upchiapas.edu.mx",
            full_name="Carga de archivos",
            password="password-seguro",
            roles={Role.PLANEACION},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "carga-archivos@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _docx(*, con_documento: bool = True, con_tipo: bool = True) -> bytes:
    """Un `.docx` mínimo: un ZIP con el manifiesto y el documento de Word."""
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w") as contenedor:
        tipo = (
            '<Override PartName="/word/document.xml" ContentType="application/vnd'
            '.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            if con_tipo
            else ""
        )
        contenedor.writestr("[Content_Types].xml", f"<Types>{tipo}</Types>")
        if con_documento:
            contenedor.writestr("word/document.xml", "<w:document/>")
    return salida.getvalue()


def _zip_cualquiera() -> bytes:
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w") as contenedor:
        contenedor.writestr("cualquier-cosa.txt", "hola")
    return salida.getvalue()


@pytest.mark.asyncio
async def test_el_formato_del_informe_se_puede_subir(client, app, tmp_path):
    """Sin esto la plantilla del informe es inservible: el área la descarga en
    Word, la completa y al adjuntarla rebotaba con un 415."""
    app.state.settings.upload_directory = str(tmp_path)
    headers = await _headers(client, app)

    subido = await client.post(
        "/api/v1/archivos",
        files={"archivo": ("informe.docx", _docx(), "application/octet-stream")},
        headers=headers,
    )

    assert subido.status_code == 201, subido.text
    assert subido.json()["mime_type"] == DOCX_MIME
    assert subido.json()["ruta"].endswith(".docx")


@pytest.mark.asyncio
async def test_un_zip_cualquiera_no_pasa_por_docx(client, app, tmp_path):
    """Un `.docx` es un ZIP, y aceptar «cualquier cosa que empiece por PK»
    abriría la puerta a todo archivo comprimido, incluido un `.xlsm` con
    macros. Por eso se abre el contenedor y se mira lo que trae dentro."""
    app.state.settings.upload_directory = str(tmp_path)
    headers = await _headers(client, app)

    for nombre, contenido in (
        ("disfrazado.docx", _zip_cualquiera()),
        ("sin-documento.docx", _docx(con_documento=False)),
        ("sin-tipo.docx", _docx(con_tipo=False)),
    ):
        rechazado = await client.post(
            "/api/v1/archivos",
            files={"archivo": (nombre, contenido, "application/octet-stream")},
            headers=headers,
        )
        assert rechazado.status_code == 415, f"{nombre}: {rechazado.text}"


@pytest.mark.asyncio
async def test_el_docx_se_descarga_con_su_tipo(client, app, tmp_path):
    app.state.settings.upload_directory = str(tmp_path)
    headers = await _headers(client, app)
    subido = await client.post(
        "/api/v1/archivos",
        files={"archivo": ("informe.docx", _docx(), "application/octet-stream")},
        headers=headers,
    )
    assert subido.status_code == 201, subido.text

    # Sin evidencia vinculada el archivo no se entrega: la descarga comprueba
    # el vínculo antes que el tipo, y eso no cambia por admitir Word.
    descarga = await client.get(f"/api/v1/archivos/{subido.json()['ruta']}", headers=headers)
    assert descarga.status_code == 404, descarga.text


@pytest.mark.asyncio
async def test_lo_que_no_es_un_formato_conocido_sigue_rebotando(client, app, tmp_path):
    app.state.settings.upload_directory = str(tmp_path)
    headers = await _headers(client, app)

    rechazado = await client.post(
        "/api/v1/archivos",
        files={"archivo": ("script.sh", b"#!/bin/sh\nrm -rf /", "application/pdf")},
        headers=headers,
    )

    assert rechazado.status_code == 415, rechazado.text
