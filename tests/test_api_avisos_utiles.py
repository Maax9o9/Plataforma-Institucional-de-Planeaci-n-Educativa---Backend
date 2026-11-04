from __future__ import annotations

import zipfile
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest

from app.modules.identity_access.domain.value_objects import Role
from app.modules.notifications.application.area_notices import (
    AVISO_DE_PLANEACION,
    CUANTOS_ADJUNTOS_CABEN,
    EL_MISMO_ADJUNTO_DOS_VECES,
    LA_VIGENCIA_DEL_AVISO_YA_PASO,
    LARGO_DEL_DESTINO,
    LARGO_DEL_NOMBRE_DEL_ADJUNTO,
    el_adjunto_del_aviso_no_esta_cargado,
)
from app.modules.notifications.domain.entities import Notification
from app.shared.domain.archivos_cargados import DOCX_MIME
from app.shared.domain.calendar import institutional_today
from helpers import API

AVISOS = f"{API}/avisos"
ARCHIVOS = f"{API}/archivos"
NOTIFICACIONES = f"{API}/notificaciones"

HOY = institutional_today()
AYER = HOY - timedelta(days=1)
MANANA = HOY + timedelta(days=1)

ROLES_QUE_REDACTAN_AVISOS = [Role.PLANEACION, Role.PLANEACION_ADMIN, Role.ADMIN_SISTEMA]

ROLES_QUE_NO_REDACTAN_AVISOS = [
    Role.CAPTURISTA_POA,
    Role.RESPONSABLE_AREA,
    Role.REVISOR_POA,
    Role.RECTORIA,
    Role.CONSULTA,
]

#: Lo que `GET /avisos` devuelve de cada comunicado. La lista va escrita entera
#: porque lo que esta prueba defiende es lo que **no** está: ni una llave que
#: nombre a una persona.
LOS_CAMPOS_DE_UN_AVISO_REDACTADO = {
    "id",
    "titulo",
    "mensaje",
    "destino_ruta",
    "vigente_hasta",
    "creado_por",
    "creado_en",
    "adjuntos",
    "entregados",
    "leidos",
    "por_area",
}

UN_PDF = b"%PDF-1.7\n" + b"0" * 64


def _docx() -> bytes:
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w") as contenedor:
        contenedor.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/word/document.xml" ContentType="application/vnd'
            '.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        contenedor.writestr("word/document.xml", "<w:document/>")
    return salida.getvalue()


async def _cargar(client, cabeceras, nombre: str, contenido: bytes) -> dict:
    subido = await client.post(
        ARCHIVOS,
        files={"archivo": (nombre, contenido, "application/octet-stream")},
        headers=cabeceras,
    )
    assert subido.status_code == 201, subido.text
    return subido.json()


async def _redactar(
    client,
    cabeceras,
    *,
    areas,
    titulo="Entrega del Programa Operativo Anual",
    mensaje="Las áreas entregan su Programa Operativo Anual antes del cierre del periodo.",
    **extra,
):
    return await client.post(
        AVISOS,
        headers=cabeceras,
        json={"areas": areas, "titulo": titulo, "mensaje": mensaje, **extra},
    )


async def _los_avisos(client, cabeceras) -> list[dict]:
    respuesta = await client.get(AVISOS, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _los_ids_de_los_avisos(client, cabeceras) -> set[int]:
    return {uno["id"] for uno in await _los_avisos(client, cabeceras)}


async def _el_aviso(client, cabeceras, aviso_id: int) -> dict:
    return next(uno for uno in await _los_avisos(client, cabeceras) if uno["id"] == aviso_id)


async def _el_buzon(client, cabeceras, *, solo_pendientes: bool = False) -> list[dict]:
    respuesta = await client.get(
        NOTIFICACIONES, headers=cabeceras, params={"no_leidas": solo_pendientes}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _leer(client, cabeceras, notificacion_id: int) -> None:
    leido = await client.post(f"{NOTIFICACIONES}/{notificacion_id}/leer", headers=cabeceras)
    assert leido.status_code == 204, leido.text


# ── El documento que el comunicado lleva ─────────────────────────────────────


async def test_el_aviso_lleva_el_formato_adjunto_y_el_area_lo_recibe_descrito(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    cargado = await _cargar(client, planeacion_headers, "formato.docx", _docx())

    redactado = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[{"nombre": "Formato del Programa Operativo Anual.docx", "ruta": cargado["ruta"]}],
    )

    assert redactado.status_code == 200, redactado.text
    recibido = (await _el_buzon(client, quien_captura))[0]
    assert recibido["adjuntos"] == [
        {
            "nombre": "Formato del Programa Operativo Anual.docx",
            "ruta_o_url": cargado["ruta"],
            "mime_type": DOCX_MIME,
            "tamanio_bytes": cargado["tamanio_bytes"],
        }
    ]


async def test_un_aviso_lleva_el_oficio_y_el_formato_y_no_uno_de_los_dos(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    oficio = await _cargar(client, planeacion_headers, "oficio.pdf", UN_PDF)
    formato = await _cargar(client, planeacion_headers, "formato.docx", _docx())

    redactado = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[
            {"nombre": "Oficio de la Dirección de Planeación.pdf", "ruta": oficio["ruta"]},
            {"nombre": "Formato del Programa Operativo Anual.docx", "ruta": formato["ruta"]},
        ],
    )

    assert redactado.status_code == 200, redactado.text
    recibido = (await _el_buzon(client, quien_captura))[0]
    assert [uno["ruta_o_url"] for uno in recibido["adjuntos"]] == [
        oficio["ruta"],
        formato["ruta"],
    ]
    assert [uno["mime_type"] for uno in recibido["adjuntos"]] == ["application/pdf", DOCX_MIME]


async def test_un_aviso_sin_ningun_adjunto_se_entrega_igual_y_la_lista_llega_vacia(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await _redactar(client, planeacion_headers, areas=[area])

    assert redactado.status_code == 200, redactado.text
    assert redactado.json()["entregados"] == 1
    recibido = (await _el_buzon(client, quien_captura))[0]
    assert recibido["adjuntos"] == []
    assert recibido["mensaje"] == (
        "Las áreas entregan su Programa Operativo Anual antes del cierre del periodo."
    )
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["adjuntos"] == []


async def test_un_aviso_sin_la_llave_de_los_adjuntos_se_entrega_igual(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await client.post(
        AVISOS,
        headers=planeacion_headers,
        json={"areas": [area], "titulo": "Un aviso", "mensaje": "El cuerpo del aviso."},
    )

    assert redactado.status_code == 200, redactado.text
    assert (await _el_buzon(client, quien_captura))[0]["adjuntos"] == []


async def test_un_adjunto_que_no_esta_cargado_se_rechaza_diciendo_cual_y_no_avisa_a_nadie(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    fantasma = f"{uuid4().hex}.pdf"
    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[{"nombre": "El formato que nadie subió.pdf", "ruta": fantasma}],
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["message"] == el_adjunto_del_aviso_no_esta_cargado(fantasma)
    assert await _el_buzon(client, quien_captura) == []
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


@pytest.mark.parametrize(
    "ruta",
    [
        pytest.param("../../../etc/passwd", id="fuera_del_directorio"),
        pytest.param("a" * 32 + ".exe", id="tipo_que_el_sistema_no_admite"),
        pytest.param("a" * 32 + ".xlsm", id="hoja_de_calculo_con_macros"),
        pytest.param("formato.pdf", id="nombre_que_no_es_el_que_la_carga_devuelve"),
        pytest.param("A" * 32 + ".pdf", id="identificador_en_mayusculas"),
    ],
)
async def test_una_ruta_que_la_carga_de_archivos_no_devolveria_se_rechaza(
    backend_client, planeacion_headers, nueva_area, ruta
):
    _, client = backend_client
    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[{"nombre": "Un documento cualquiera", "ruta": ruta}],
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


async def test_el_mismo_documento_adjunto_dos_veces_se_rechaza(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    cargado = await _cargar(client, planeacion_headers, "formato.docx", _docx())
    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[
            {"nombre": "El formato", "ruta": cargado["ruta"]},
            {"nombre": "El formato otra vez", "ruta": cargado["ruta"]},
        ],
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["message"] == EL_MISMO_ADJUNTO_DOS_VECES
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


@pytest.mark.parametrize("nombre", ["", "   "])
async def test_un_adjunto_sin_nombre_que_leer_se_rechaza(
    backend_client, planeacion_headers, nueva_area, nombre
):
    _, client = backend_client
    cargado = await _cargar(client, planeacion_headers, "formato.docx", _docx())
    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[{"nombre": nombre, "ruta": cargado["ruta"]}],
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


async def test_el_nombre_del_adjunto_cabe_en_trescientos_caracteres_y_no_en_trescientos_uno(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    cargado = await _cargar(client, planeacion_headers, "formato.docx", _docx())

    cabe = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[{"nombre": "n" * LARGO_DEL_NOMBRE_DEL_ADJUNTO, "ruta": cargado["ruta"]}],
    )
    no_cabe = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[{"nombre": "n" * (LARGO_DEL_NOMBRE_DEL_ADJUNTO + 1), "ruta": cargado["ruta"]}],
    )

    assert cabe.status_code == 200, cabe.text
    assert no_cabe.status_code == 422, no_cabe.text


async def test_mas_adjuntos_de_los_que_caben_se_rechazan(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    cargados = [
        await _cargar(client, planeacion_headers, f"formato-{numero}.docx", _docx())
        for numero in range(CUANTOS_ADJUNTOS_CABEN + 1)
    ]

    cabe = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[
            {"nombre": f"Documento {numero}", "ruta": uno["ruta"]}
            for numero, uno in enumerate(cargados[:-1])
        ],
    )
    no_cabe = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[
            {"nombre": f"Documento {numero}", "ruta": uno["ruta"]}
            for numero, uno in enumerate(cargados)
        ],
    )

    assert cabe.status_code == 200, cabe.text
    assert no_cabe.status_code == 422, no_cabe.text


async def test_un_campo_que_el_adjunto_no_declara_se_rechaza(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    cargado = await _cargar(client, planeacion_headers, "formato.docx", _docx())

    respuesta = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        adjuntos=[
            {
                "nombre": "El formato",
                "ruta": cargado["ruta"],
                "tamanio_bytes": 1,
            }
        ],
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_el_tamanio_del_adjunto_lo_mide_el_sistema_y_no_lo_dice_quien_redacta(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    contenido = _docx()
    cargado = await _cargar(client, planeacion_headers, "formato.docx", contenido)

    await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        adjuntos=[{"nombre": "El formato", "ruta": cargado["ruta"]}],
    )

    recibido = (await _el_buzon(client, quien_captura))[0]
    assert recibido["adjuntos"][0]["tamanio_bytes"] == len(contenido)


# ── El destino del comunicado ────────────────────────────────────────────────


async def test_el_aviso_dice_a_que_pantalla_del_sistema_se_refiere(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await _redactar(
        client, planeacion_headers, areas=[area], destino_ruta="/poa-institucional/mi-area"
    )

    assert redactado.status_code == 200, redactado.text
    assert (await _el_buzon(client, quien_captura))[0][
        "destino_ruta"
    ] == "/poa-institucional/mi-area"
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["destino_ruta"] == "/poa-institucional/mi-area"


async def test_un_aviso_sin_destino_lo_devuelve_nulo_y_no_uno_inventado(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await _redactar(client, planeacion_headers, areas=[area])

    assert (await _el_buzon(client, quien_captura))[0]["destino_ruta"] is None
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["destino_ruta"] is None


@pytest.mark.parametrize(
    "destino",
    [
        pytest.param("https://otro-sitio.example.com/formato", id="sitio_de_fuera"),
        pytest.param("//otro-sitio.example.com/formato", id="ruta_que_es_un_sitio_de_fuera"),
        pytest.param("javascript:alert(1)", id="guion_que_el_navegador_ejecutaria"),
        pytest.param("poa-institucional", id="ruta_sin_la_barra_de_inicio"),
    ],
)
async def test_un_destino_que_no_es_una_pantalla_del_sistema_se_rechaza(
    backend_client, planeacion_headers, nueva_area, destino
):
    _, client = backend_client
    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client, planeacion_headers, areas=[await nueva_area()], destino_ruta=destino
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


async def test_un_destino_con_holgura_alrededor_se_recorta_y_se_admite(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client

    redactado = await _redactar(
        client,
        planeacion_headers,
        areas=[await nueva_area()],
        destino_ruta="  /poa-institucional  ",
    )

    assert redactado.status_code == 200, redactado.text
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["destino_ruta"] == "/poa-institucional"


async def test_un_destino_que_es_solo_holgura_se_guarda_como_sin_destino(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client

    redactado = await _redactar(
        client, planeacion_headers, areas=[await nueva_area()], destino_ruta="   "
    )

    assert redactado.status_code == 200, redactado.text
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["destino_ruta"] is None


async def test_un_destino_vacio_se_rechaza_antes_de_llegar_al_dominio(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client

    respuesta = await _redactar(
        client, planeacion_headers, areas=[await nueva_area()], destino_ruta=""
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_el_destino_cabe_en_doscientos_caracteres_y_no_en_doscientos_uno(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    area = await nueva_area()

    cabe = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        destino_ruta="/" + "a" * (LARGO_DEL_DESTINO - 1),
    )
    no_cabe = await _redactar(
        client, planeacion_headers, areas=[area], destino_ruta="/" + "a" * LARGO_DEL_DESTINO
    )

    assert cabe.status_code == 200, cabe.text
    assert no_cabe.status_code == 422, no_cabe.text


# ── La vigencia del comunicado ───────────────────────────────────────────────


async def test_el_aviso_dice_hasta_cuando_sigue_aplicando(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await _redactar(
        client, planeacion_headers, areas=[area], vigente_hasta=MANANA.isoformat()
    )

    assert redactado.status_code == 200, redactado.text
    assert (await _el_buzon(client, quien_captura))[0]["vigente_hasta"] == MANANA.isoformat()
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["vigente_hasta"] == MANANA.isoformat()


async def test_un_aviso_sin_vigencia_la_devuelve_nula_y_no_una_inventada(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    await _redactar(client, planeacion_headers, areas=[area])

    assert (await _el_buzon(client, quien_captura))[0]["vigente_hasta"] is None


async def test_una_vigencia_que_ya_paso_se_rechaza_y_no_avisa_a_nadie(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    antes = await _los_ids_de_los_avisos(client, planeacion_headers)

    respuesta = await _redactar(
        client, planeacion_headers, areas=[area], vigente_hasta=AYER.isoformat()
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["message"] == LA_VIGENCIA_DEL_AVISO_YA_PASO
    assert await _el_buzon(client, quien_captura) == []
    assert await _los_ids_de_los_avisos(client, planeacion_headers) == antes


async def test_un_aviso_que_vence_hoy_todavia_se_redacta_porque_hoy_cuenta(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    redactado = await _redactar(
        client, planeacion_headers, areas=[area], vigente_hasta=HOY.isoformat()
    )

    assert redactado.status_code == 200, redactado.text
    assert len(await _el_buzon(client, quien_captura, solo_pendientes=True)) == 1


async def test_un_aviso_vencido_se_sigue_consultando_y_no_se_borra(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    redactado = await _redactar(
        client, planeacion_headers, areas=[area], vigente_hasta=HOY.isoformat()
    )

    app.state.el_buzon.today = lambda: HOY + timedelta(days=2)

    todos = await _el_buzon(client, quien_captura)
    assert [uno["vigente_hasta"] for uno in todos] == [HOY.isoformat()]
    assert todos[0]["leida"] is False
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["vigente_hasta"] == HOY.isoformat()
    assert consultado["entregados"] == 1


async def test_un_aviso_vencido_deja_de_contar_como_pendiente(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _redactar(client, planeacion_headers, areas=[area], vigente_hasta=HOY.isoformat())

    app.state.el_buzon.today = lambda: HOY + timedelta(days=1)

    assert await _el_buzon(client, quien_captura, solo_pendientes=True) == []


async def test_un_aviso_sin_vigencia_sigue_pendiente_pase_el_tiempo_que_pase(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _redactar(client, planeacion_headers, areas=[area])

    app.state.el_buzon.today = lambda: HOY + timedelta(days=3650)

    assert len(await _el_buzon(client, quien_captura, solo_pendientes=True)) == 1


async def test_una_notificacion_que_no_nace_de_un_comunicado_no_la_esconde_ninguna_vigencia(
    backend_client, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    cabeceras = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    yo = next(uno for uno in await app.state.user_repository.list() if uno.area_id == area)
    await app.state.notification_repository.create(
        Notification(
            user_id=yo.id,
            notification_type="recordatorio_5d",
            message="El periodo de captura vence en cinco días.",
        )
    )

    app.state.el_buzon.today = lambda: HOY + timedelta(days=3650)

    pendientes = await _el_buzon(client, cabeceras, solo_pendientes=True)
    assert [uno["tipo"] for uno in pendientes] == ["recordatorio_5d"]
    assert pendientes[0]["aviso_id"] is None
    assert pendientes[0]["adjuntos"] == []
    assert pendientes[0]["destino_ruta"] is None
    assert pendientes[0]["vigente_hasta"] is None


# ── Quién leyó el comunicado que la Dirección de Planeación mandó ────────────


async def test_un_comunicado_dirigido_a_dos_areas_es_un_solo_comunicado(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    una = await nueva_area()
    otra = await nueva_area()
    nombre_de_una = (await app.state.area_repository.get_by_id(una)).name
    nombre_de_otra = (await app.state.area_repository.get_by_id(otra)).name
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=una)
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=una)
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=otra)

    redactado = await _redactar(client, planeacion_headers, areas=[una, otra])

    de_las_dos = [
        uno
        for uno in await _los_avisos(client, planeacion_headers)
        if any(area["area_id"] in {una, otra} for area in uno["por_area"])
    ]
    assert [uno["id"] for uno in de_las_dos] == [redactado.json()["aviso_id"]]
    assert (de_las_dos[0]["entregados"], de_las_dos[0]["leidos"]) == (3, 0)
    assert de_las_dos[0]["por_area"] == [
        {"area_id": una, "area": nombre_de_una, "entregados": 2, "leidos": 0},
        {"area_id": otra, "area": nombre_de_otra, "entregados": 1, "leidos": 0},
    ]


async def test_las_cifras_dicen_cuantos_de_cuantos_leyeron_el_comunicado(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=area)
    redactado = await _redactar(client, planeacion_headers, areas=[area])
    mio = (await _el_buzon(client, quien_captura))[0]

    await _leer(client, quien_captura, mio["id"])

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert (consultado["entregados"], consultado["leidos"]) == (2, 1)
    assert consultado["por_area"] == [
        {"area_id": area, "area": consultado["por_area"][0]["area"], "entregados": 2, "leidos": 1}
    ]


async def test_el_conteo_de_leidos_cuenta_las_entregas_de_ese_comunicado_y_no_todas(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    primero = await _redactar(client, planeacion_headers, areas=[area], titulo="El primer aviso")
    segundo = await _redactar(client, planeacion_headers, areas=[area], titulo="El segundo aviso")
    del_primero = next(
        uno
        for uno in await _el_buzon(client, quien_captura)
        if uno["aviso_id"] == primero.json()["aviso_id"]
    )

    await _leer(client, quien_captura, del_primero["id"])

    por_id = {uno["id"]: uno for uno in await _los_avisos(client, planeacion_headers)}
    assert por_id[primero.json()["aviso_id"]]["leidos"] == 1
    assert por_id[segundo.json()["aviso_id"]]["leidos"] == 0
    assert por_id[segundo.json()["aviso_id"]]["entregados"] == 1
    assert por_id[primero.json()["aviso_id"]]["por_area"][0]["leidos"] == 1
    assert por_id[segundo.json()["aviso_id"]]["por_area"][0]["leidos"] == 0


async def test_las_cifras_de_un_comunicado_no_cuentan_las_entregas_de_otro_area(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    una = await nueva_area()
    otra = await nueva_area()
    de_una = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=una)
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=otra)
    redactado = await _redactar(client, planeacion_headers, areas=[una, otra])
    mio = (await _el_buzon(client, de_una))[0]

    await _leer(client, de_una, mio["id"])

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    por_area = {uno["area_id"]: uno for uno in consultado["por_area"]}
    assert por_area[una]["leidos"] == 1
    assert por_area[otra]["leidos"] == 0


async def test_un_recordatorio_no_aparece_entre_los_comunicados_ni_cuenta_como_entrega(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    yo = next(uno for uno in await app.state.user_repository.list() if uno.area_id == area)
    antes = await _los_avisos(client, planeacion_headers)

    await app.state.notification_repository.create(
        Notification(
            user_id=yo.id,
            notification_type="recordatorio_5d",
            message="El periodo de captura vence en cinco días.",
        )
    )

    assert await _los_avisos(client, planeacion_headers) == antes


async def test_un_comunicado_sin_nadie_a_quien_avisarle_se_consulta_con_las_cifras_en_cero(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    await cuenta_con_rol(Role.CONSULTA, area_id=area)

    redactado = await _redactar(client, planeacion_headers, areas=[area])

    assert redactado.status_code == 200, redactado.text
    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert (consultado["entregados"], consultado["leidos"]) == (0, 0)
    assert consultado["por_area"] == []


async def test_los_comunicados_se_consultan_del_mas_reciente_al_mas_antiguo(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    primero = await _redactar(client, planeacion_headers, areas=[area], titulo="El primer aviso")
    segundo = await _redactar(client, planeacion_headers, areas=[area], titulo="El segundo aviso")
    los_dos = {primero.json()["aviso_id"], segundo.json()["aviso_id"]}

    redactados = [
        uno for uno in await _los_avisos(client, planeacion_headers) if uno["id"] in los_dos
    ]

    assert [uno["titulo"] for uno in redactados] == ["El segundo aviso", "El primer aviso"]


async def test_el_comunicado_dice_quien_lo_redacto(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    de_antes = {uno.id for uno in await app.state.user_repository.list()}
    cabeceras = await cuenta_con_rol(Role.PLANEACION_ADMIN, area_id=None)
    quien = next(uno for uno in await app.state.user_repository.list() if uno.id not in de_antes)

    redactado = await _redactar(client, cabeceras, areas=[await nueva_area()])

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["creado_por"] == quien.id


async def test_las_cifras_de_lectura_no_dicen_quien_leyo_y_quien_no_persona_por_persona(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    redactado = await _redactar(client, planeacion_headers, areas=[area])
    mio = (await _el_buzon(client, quien_captura))[0]
    await _leer(client, quien_captura, mio["id"])

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])

    assert set(consultado) == LOS_CAMPOS_DE_UN_AVISO_REDACTADO
    assert set(consultado["por_area"][0]) == {"area_id", "area", "entregados", "leidos"}
    sin_personas = str(consultado).lower()
    for palabra in ("usuario", "persona", "correo", "nombre_completo"):
        assert palabra not in sin_personas


async def test_la_entrega_a_una_cuenta_dada_de_baja_sigue_contando_en_su_area(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    nombre = (await app.state.area_repository.get_by_id(area)).name
    de_antes = {uno.id for uno in await app.state.user_repository.list()}
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    redactado = await _redactar(client, planeacion_headers, areas=[area])
    mio = (await _el_buzon(client, quien_captura))[0]
    await _leer(client, quien_captura, mio["id"])
    quien = next(uno for uno in await app.state.user_repository.list() if uno.id not in de_antes)

    quien.is_active = False
    await app.state.user_repository.update(quien)

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["por_area"] == [
        {"area_id": area, "area": nombre, "entregados": 1, "leidos": 1}
    ]


async def test_el_comunicado_de_un_area_retirada_sigue_diciendo_de_que_area_era(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area_id = await nueva_area()
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area_id)
    redactado = await _redactar(client, planeacion_headers, areas=[area_id])
    area = await app.state.area_repository.get_by_id(area_id)

    area.is_active = False
    await app.state.area_repository.update(area)

    consultado = await _el_aviso(client, planeacion_headers, redactado.json()["aviso_id"])
    assert consultado["por_area"] == [
        {"area_id": area_id, "area": area.name, "entregados": 1, "leidos": 0}
    ]


async def test_las_entregas_que_el_repositorio_devuelve_son_las_del_aviso_que_se_le_pide(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    primero = (
        await _redactar(client, planeacion_headers, areas=[area], titulo="El primer aviso")
    ).json()["aviso_id"]
    segundo = (
        await _redactar(client, planeacion_headers, areas=[area], titulo="El segundo aviso")
    ).json()["aviso_id"]
    yo = next(uno for uno in await app.state.user_repository.list() if uno.area_id == area)
    mio = next(uno for uno in await _el_buzon(client, quien_captura) if uno["aviso_id"] == primero)
    await _leer(client, quien_captura, mio["id"])

    del_primero = await app.state.notification_repository.deliveries_of([primero])

    assert [(una.aviso_id, una.usuario_id, una.leida) for una in del_primero] == [
        (primero, yo.id, True)
    ]
    assert [
        (una.aviso_id, una.leida)
        for una in await app.state.notification_repository.deliveries_of([segundo])
    ] == [(segundo, False)]
    assert await app.state.notification_repository.deliveries_of([]) == []


# ── Quién consulta las cifras de lectura y quién no ──────────────────────────


@pytest.mark.parametrize("rol", ROLES_QUE_REDACTAN_AVISOS)
async def test_quien_redacta_los_avisos_consulta_sus_cifras_de_lectura(
    backend_client, cuenta_con_rol, rol
):
    _, client = backend_client
    cabeceras = await cuenta_con_rol(rol, area_id=None)

    respuesta = await client.get(AVISOS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", ROLES_QUE_NO_REDACTAN_AVISOS)
async def test_quien_no_redacta_los_avisos_no_consulta_sus_cifras_de_lectura(
    backend_client, nueva_area, cuenta_con_rol, rol
):
    _, client = backend_client
    cabeceras = await cuenta_con_rol(rol, area_id=await nueva_area())

    respuesta = await client.get(AVISOS, headers=cabeceras)

    assert respuesta.status_code == 403, respuesta.text


async def test_sin_sesion_no_se_consultan_las_cifras_de_lectura(backend_client):
    _, client = backend_client

    respuesta = await client.get(AVISOS)

    assert respuesta.status_code == 401, respuesta.text


async def test_el_area_que_recibio_el_comunicado_no_ve_las_cifras_de_quien_lo_leyo(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _redactar(client, planeacion_headers, areas=[area])

    assert len(await _el_buzon(client, quien_captura)) == 1
    assert (await client.get(AVISOS, headers=quien_captura)).status_code == 403


# ── El contrato del OpenAPI ──────────────────────────────────────────────────


async def test_el_comunicado_declara_sus_campos_nuevos_en_el_openapi(app):
    esquema = app.openapi()

    cuerpo = esquema["components"]["schemas"]["AvisoDePlaneacionRequest"]
    assert sorted(cuerpo["required"]) == ["areas", "mensaje", "titulo"]
    assert cuerpo["additionalProperties"] is False
    assert set(cuerpo["properties"]) == {
        "areas",
        "titulo",
        "mensaje",
        "destino_ruta",
        "vigente_hasta",
        "adjuntos",
    }
    assert cuerpo["properties"]["adjuntos"]["maxItems"] == CUANTOS_ADJUNTOS_CABEN

    adjunto = esquema["components"]["schemas"]["AdjuntoDelAvisoRequest"]
    assert sorted(adjunto["required"]) == ["nombre", "ruta"]
    assert adjunto["additionalProperties"] is False
    assert adjunto["properties"]["nombre"]["maxLength"] == LARGO_DEL_NOMBRE_DEL_ADJUNTO


async def test_las_cifras_de_lectura_declaran_su_contrato_en_el_openapi(app):
    esquema = app.openapi()

    consultar = esquema["paths"][AVISOS]["get"]
    lista = consultar["responses"]["200"]["content"]["application/json"]["schema"]
    assert lista["type"] == "array"
    assert lista["items"]["$ref"].endswith("AvisoRedactadoRespuesta")
    assert consultar["security"] != []
    assert {"401", "403", "500", "503"} <= set(consultar["responses"])

    respuesta = esquema["components"]["schemas"]["AvisoRedactadoRespuesta"]
    assert sorted(respuesta["required"]) == sorted(LOS_CAMPOS_DE_UN_AVISO_REDACTADO)

    por_area = esquema["components"]["schemas"]["LecturaPorAreaRespuesta"]
    assert sorted(por_area["required"]) == ["area", "area_id", "entregados", "leidos"]

    adjunto = esquema["components"]["schemas"]["AdjuntoRespuesta"]
    assert sorted(adjunto["required"]) == [
        "mime_type",
        "nombre",
        "ruta_o_url",
        "tamanio_bytes",
    ]


async def test_la_notificacion_declara_los_campos_del_comunicado_en_el_openapi(app):
    esquema = app.openapi()

    notificacion = esquema["components"]["schemas"]["NotificacionRespuesta"]

    assert {"aviso_id", "destino_ruta", "vigente_hasta", "adjuntos"} <= set(
        notificacion["required"]
    )
    assert notificacion["properties"]["adjuntos"]["items"]["$ref"].endswith("AdjuntoRespuesta")
    assert notificacion["properties"]["aviso_id"]["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]


# ── Lo que el comunicado no cambió ───────────────────────────────────────────


async def test_el_origen_del_evento_sigue_evitando_que_el_mismo_reparto_se_repita(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    primero = await _redactar(client, planeacion_headers, areas=[area], titulo="El mismo aviso")
    segundo = await _redactar(client, planeacion_headers, areas=[area], titulo="El mismo aviso")

    assert primero.json()["aviso_id"] != segundo.json()["aviso_id"]
    recibidos = await _el_buzon(client, quien_captura)
    assert len(recibidos) == 2
    assert {uno["aviso_id"] for uno in recibidos} == {
        primero.json()["aviso_id"],
        segundo.json()["aviso_id"],
    }


async def test_la_entrega_del_aviso_de_la_apertura_no_apunta_a_ningun_comunicado(
    backend_client, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    cabeceras = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    yo = next(uno for uno in await app.state.user_repository.list() if uno.area_id == area)
    await app.state.notification_repository.create(
        Notification(
            user_id=yo.id,
            notification_type=AVISO_DE_PLANEACION,
            title="Un aviso de antes del comunicado",
            message="El cuerpo del aviso.",
        )
    )

    recibidos = await _el_buzon(client, cabeceras)

    assert [uno["aviso_id"] for uno in recibidos] == [None]
    assert [uno["adjuntos"] for uno in recibidos] == [[]]
