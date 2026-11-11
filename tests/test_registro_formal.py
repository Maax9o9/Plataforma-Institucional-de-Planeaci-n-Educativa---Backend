from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.modules.poa_institucional.domain.entities import (
    EL_AREA_NO_EXISTE,
    EL_AREA_YA_TIENE_SU_POA,
    EL_POA_DEL_AREA_NO_EXISTE,
    LA_ACTIVIDAD_LA_MOVIERON,
    LO_MOVIERON_AL_ENVIAR,
)
from app.modules.poa_planning.api.cedula_router import EL_SEGUIMIENTO_NO_ES_DEL_AREA
from app.modules.poa_planning.domain.entities import EL_EJERCICIO_POA_NO_EXISTE

RAIZ = Path(__file__).resolve().parent.parent
APLICACION = RAIZ / "app"
PLANTILLAS_DE_CORREO = APLICACION / "modules/email_templates/infrastructure/templates/messages"

PRONOMBRES_DE_TU = (
    "tu",
    "tus",
    "tuyo",
    "tuya",
    "tuyos",
    "tuyas",
    "ti",
    "te",
    "contigo",
)

VERBOS_EN_SEGUNDA_PERSONA = (
    "puedes",
    "tienes",
    "debes",
    "quieres",
    "estás",
    "eres",
    "necesitas",
    "sabes",
    "podrás",
    "tendrás",
    "deberás",
    "verás",
    "harás",
)

IMPERATIVOS_DE_TU = (
    "selecciona",
    "captura",
    "carga",
    "agrega",
    "revisa",
    "verifica",
    "elige",
    "ingresa",
    "intenta",
    "inténtalo",
    "vuelve",
    "corrige",
    "envía",
    "guarda",
    "contacta",
    "comunícate",
    "solicita",
    "asigna",
    "espera",
    "usa",
    "escribe",
    "indica",
    "actualiza",
    "consulta",
    "descarga",
    "completa",
    "configura",
    "repite",
    "crea",
    "abre",
    "añade",
    "comparte",
)

PRIMERA_PERSONA = (
    "mi",
    "mis",
    "mío",
    "mía",
    "nos",
    "nuestro",
    "nuestra",
    "nuestros",
    "nuestras",
    "estamos",
    "tenemos",
    "podemos",
    "queremos",
    "sabemos",
    "hicimos",
    "vamos",
    "comencemos",
    "completemos",
    "revisemos",
    "esperándonos",
)

ABRE_LA_ORACION = (". ", ": ", "! ", "? ", "¡", "¿", "» ", ") ", "\n")


def _como_se_escriba(forma: str) -> re.Pattern[str]:
    inicial = forma[0]
    return re.compile(rf"\b[{inicial}{inicial.upper()}]{re.escape(forma[1:])}\b")


DONDE_SEA = tuple(
    (forma, _como_se_escriba(forma))
    for forma in (*PRONOMBRES_DE_TU, *VERBOS_EN_SEGUNDA_PERSONA, *PRIMERA_PERSONA)
)

SOLO_AL_ABRIR_LA_ORACION = tuple((forma, _como_se_escriba(forma)) for forma in IMPERATIVOS_DE_TU)


def _abre_la_oracion(texto: str, posicion: int) -> bool:
    anterior = texto[:posicion]
    return anterior == "" or anterior.isspace() or anterior.endswith(ABRE_LA_ORACION)


def formas_en(texto: str) -> list[str]:
    halladas = [forma for forma, patron in DONDE_SEA if patron.search(texto)]
    halladas += [
        forma
        for forma, patron in SOLO_AL_ABRIR_LA_ORACION
        if any(_abre_la_oracion(texto, hallada.start()) for hallada in patron.finditer(texto))
    ]
    return sorted(set(halladas))


@dataclass(frozen=True)
class Excepcion:
    archivo: str
    texto: str
    porque: str


EL_CORPUS_DE_LOS_CORREOS = (
    "Los catorce mensajes de correo quedan en el registro anterior y se corrigen juntos: su texto"
    " por omisión vive en los archivos JSON de las plantillas, pero la plataforma admite"
    " sobrescribirlo desde la administración, así que corregir el archivo no cambia lo que ya está"
    " guardado. Mientras el corpus entero siga en el registro anterior, los textos de prueba que"
    " lo imitan tienen que imitarlo tal cual, o la vista previa mentiría sobre lo que se envía."
)

LO_QUE_FALTA_POR_CORREGIR: tuple[Excepcion, ...] = (
    Excepcion(
        archivo="core/app_factory.py",
        texto="Usa SQLAlchemy async cuando DATABASE_URL",
        porque="No es texto de pantalla: es la descripción de la interfaz de programación que se"
        " publica en /docs, y la lee quien integra un sistema con la plataforma. Nombra"
        " DATABASE_URL y el motor de persistencia, que son tripas, justamente porque su"
        " destinatario las necesita.",
    ),
    Excepcion(
        archivo="core/cors.py",
        texto="Usa una URL como",
        porque="Es el error con que el servidor se niega a arrancar si la configuración de"
        " orígenes permitidos está mal escrita. Lo lee quien despliega, en la consola, y nunca"
        " llega a una pantalla: el servidor no termina de levantar.",
    ),
    Excepcion(
        archivo="core/lifecycle.py",
        texto="Usa python -m app.scripts.create_admin",
        porque="Es la advertencia de arranque que señala una variable de entorno retirada y"
        " nombra el comando que la sustituye. Va al registro del servidor, no a una pantalla.",
    ),
    Excepcion(
        archivo="scripts/cargar_pide.py",
        texto="Carga el arbol del PIDE",
        porque="Es la ayuda de un programa de línea de comandos que Planeación no ejecuta:"
        " la carga del árbol del Programa Institucional de Desarrollo la hace quien administra el"
        " servidor.",
    ),
    Excepcion(
        archivo="scripts/create_admin.py",
        texto="Repite la contraseña:",
        porque="Es la indicación de un programa de línea de comandos que crea la primera cuenta"
        " administradora antes de que exista la plataforma. No hay pantalla donde mostrarla.",
    ),
    Excepcion(
        archivo="modules/email_templates/api/router.py",
        texto="Tu enlace personal vence en 24 horas",
        porque=EL_CORPUS_DE_LOS_CORREOS,
    ),
    Excepcion(
        archivo="modules/email_templates/api/router.py",
        texto="Revisa las fechas y pendientes",
        porque=EL_CORPUS_DE_LOS_CORREOS,
    ),
    Excepcion(
        archivo="modules/identity_access/application/use_cases/password_setup.py",
        texto="Tu enlace personal vence en",
        porque=EL_CORPUS_DE_LOS_CORREOS,
    ),
)

CAMPOS_DEL_CORREO = ("asunto", "titulo", "cuerpo", "texto_boton")

PLANTILLAS_DE_CORREO_QUE_HAY = 14
PLANTILLAS_EN_EL_REGISTRO_ANTERIOR = 14
CAMPOS_EN_EL_REGISTRO_ANTERIOR = 45


def _docstrings(arbol: ast.Module) -> set[str]:
    encontradas = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            texto = ast.get_docstring(nodo, clean=False)
            if texto is not None:
                encontradas.add(texto)
    return encontradas


def _parece_una_frase(texto: str) -> bool:
    return any(
        letra.isalpha() and siguiente == " "
        for letra, siguiente in zip(texto, texto[1:], strict=False)
    ) and any(letra.isalpha() for letra in texto)


def literales_de(ruta: Path) -> list[tuple[int, str]]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    sin_contar = _docstrings(arbol)
    return [
        (nodo.lineno, nodo.value)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, str)
        and nodo.value not in sin_contar
        and _parece_una_frase(nodo.value)
    ]


ARCHIVOS_DE_LA_APLICACION = sorted(
    (ruta.relative_to(APLICACION).as_posix(), ruta) for ruta in APLICACION.rglob("*.py")
)


def sin_lo_permitido(texto: str, permitidos: list[str]) -> str:
    for permitido in permitidos:
        texto = texto.replace(permitido, "")
    return texto


def registro_anterior_en(relativa: str, ruta: Path) -> list[str]:
    permitidos = [
        excepcion.texto for excepcion in LO_QUE_FALTA_POR_CORREGIR if excepcion.archivo == relativa
    ]
    hallazgos = []
    for linea, texto in literales_de(ruta):
        formas = formas_en(sin_lo_permitido(texto, permitidos))
        if formas:
            hallazgos.append(f"{relativa}:{linea}: {', '.join(formas)} → {texto[:120]}")
    return hallazgos


@pytest.mark.parametrize(
    ("texto", "forma"),
    [
        ("El seguimiento del POA no es de tu área.", "tu"),
        ("Revisa tus pendientes del periodo.", "tus"),
        ("Tu rol no permite aprobar el ejercicio.", "tu"),
        ("Este Programa Operativo Anual es tuyo.", "tuyo"),
        ("El área es tuya.", "tuya"),
        ("La actividad se asignó a ti ayer.", "ti"),
        ("El registro se te devolvió con observaciones.", "te"),
        ("Te damos la bienvenida a la plataforma.", "te"),
        ("El expediente viaja contigo.", "contigo"),
        ("No puedes validar tu propio seguimiento.", "puedes"),
        ("Tienes una actividad asignada.", "tienes"),
        ("Debes configurar la contraseña antes de entrar.", "debes"),
        ("Si quieres presentarlo, falta la meta anual.", "quieres"),
        ("Ya estás dentro del periodo de captura.", "estás"),
        ("Eres el capturista del área.", "eres"),
        ("Necesitas una unidad de medida.", "necesitas"),
        ("Ya sabes cuántas actividades faltan.", "sabes"),
        ("Podrás registrar actividades a partir de esa fecha.", "podrás"),
        ("Tendrás que esperar la apertura.", "tendrás"),
        ("Deberás adjuntar la evidencia.", "deberás"),
        ("Verás el periodo en la pantalla de inicio.", "verás"),
        ("Selecciona la acción del PIDE.", "selecciona"),
        ("Captura el seguimiento con evidencia.", "captura"),
        ("Agrega una actividad al programa.", "agrega"),
        ("Revisa sus fechas antes de guardar.", "revisa"),
        ("Verifica la programación de los doce meses.", "verifica"),
        ("Elige al menos un área.", "elige"),
        ("Ingresa la meta anual.", "ingresa"),
        ("Intenta de nuevo en unos momentos.", "intenta"),
        ("Inténtalo de nuevo en unos momentos.", "inténtalo"),
        ("Vuelve a cargarlo antes de enviarlo.", "vuelve"),
        ("Corrige la programación y guarda otra vez.", "corrige"),
        ("Envía el programa cuando esté completo.", "envía"),
        ("Guarda el avance antes de salir.", "guarda"),
        ("Contacta a la Dirección de Planeación.", "contacta"),
        ("Comunícate con la Dirección de Planeación.", "comunícate"),
        ("Solicita un periodo nuevo.", "solicita"),
        ("Asigna el rol de responsable de área.", "asigna"),
        ("Espera la apertura del periodo.", "espera"),
        ("Usa una dirección como la del ejemplo.", "usa"),
        ("Escribe el motivo de la habilitación.", "escribe"),
        ("Indica sobre qué versión se edita.", "indica"),
        ("Actualiza el catálogo de áreas.", "actualiza"),
        ("Consulta el expediente del programa.", "consulta"),
        ("Descarga el formato oficial.", "descarga"),
        ("Completa los datos de progreso.", "completa"),
        ("Configura la contraseña personal.", "configura"),
        ("Repite la contraseña escrita.", "repite"),
        ("Crea la contraseña personal.", "crea"),
        ("Abre el programa del área.", "abre"),
        ("Añade una actividad más.", "añade"),
        ("Comparte el enlace con nadie más.", "comparte"),
        ("Mi panel de captura del periodo.", "mi"),
        ("Mis capturas del cuatrimestre.", "mis"),
        ("Éste es mi panel de captura.", "mi"),
        ("Aquí están mis capturas.", "mis"),
        ("Nuestros indicadores institucionales.", "nuestros"),
        ("Los indicadores de nuestra universidad.", "nuestra"),
        ("El programa se nos venció.", "nos"),
        ("Estamos en la última semana del cuatrimestre.", "estamos"),
        ("Ya tenemos la evidencia del periodo.", "tenemos"),
        ("Todavía no podemos leer el árbol.", "podemos"),
        ("Si queremos presentarlo, falta la meta.", "queremos"),
        ("No sabemos cuántas actividades faltan.", "sabemos"),
        ("Ya hicimos el reparto entre los meses.", "hicimos"),
        ("Comencemos el seguimiento del cuatrimestre.", "comencemos"),
        ("Completemos el balance anual.", "completemos"),
        ("Revisemos la captura del área.", "revisemos"),
        ("La captura sigue esperándonos.", "esperándonos"),
    ],
)
def test_el_detector_reconoce_el_registro_anterior(texto: str, forma: str) -> None:
    assert forma in formas_en(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "El seguimiento del Programa Operativo Anual no es del área del usuario.",
        "Su perfil no permite aprobar el ejercicio del Programa Operativo Anual.",
        "El área ya tiene su Programa Operativo Anual en este ejercicio.",
        "El ejercicio del Programa Operativo Anual no existe.",
        "El área no existe. Revise el catálogo de áreas antes de continuar.",
        "La actividad fue modificada por otra solicitud. Vuelva a consultarla antes de guardar.",
        "Revise el periodo disponible y organice el registro de los indicadores asignados.",
        "Elija al menos un área para abrir su Programa Operativo Anual.",
        "El periodo de captura concluyó el 15 de octubre de 2026.",
        "Podrá registrar sus actividades a partir de esa fecha.",
        "Solicite a la Dirección de Planeación que habilite un nuevo periodo.",
        "Conserve su captura y vuelva a intentarlo en unos momentos.",
        "La Dirección de Planeación habilitó el registro de actividades.",
        "Escriba el título del aviso que recibirán las áreas.",
        "El primer periodo de captura de un Programa Operativo Anual es el número 1.",
        "La denominación de la actividad es obligatoria.",
        "Días naturales restantes del periodo",
        "Administración del sistema",
        "Misión y visión institucionales",
        "Comisión mixta de seguridad",
        "Nómina del personal adscrito",
        "Semáforo institucional",
        "Permiso denegado",
        "Consultar captura de indicador",
        "Habilitación del periodo de captura",
        "Datos de captura, no validación.",
        "Un nodo no cambia de versión.",
        "La consulta requiere un capturista con área asignada.",
        "El total alcanzado sólo se captura durante el tercer cuatrimestre.",
        "Validar captura enviada",
        "El archivo debe provenir del endpoint seguro de carga.",
    ],
)
def test_el_detector_no_se_dispara_con_el_registro_aprobado(texto: str) -> None:
    assert formas_en(texto) == []


def test_el_barrido_alcanza_el_dominio_la_api_y_las_notificaciones() -> None:
    rutas = [relativa for relativa, _ in ARCHIVOS_DE_LA_APLICACION]

    assert len(rutas) > 100
    assert "modules/poa_institucional/domain/entities.py" in rutas
    assert "modules/poa_institucional/api/router.py" in rutas
    assert "modules/poa_planning/api/cedula_router.py" in rutas
    assert "modules/poa_planning/application/use_cases/review_follow_up.py" in rutas
    assert "modules/notifications/application/service.py" in rutas
    assert "shared/domain/exceptions.py" in rutas


def test_ningun_mensaje_de_la_aplicacion_tutea_ni_habla_en_primera_persona() -> None:
    hallazgos = [
        hallazgo
        for relativa, ruta in ARCHIVOS_DE_LA_APLICACION
        for hallazgo in registro_anterior_en(relativa, ruta)
    ]

    assert hallazgos == []


def test_los_unicos_archivos_donde_el_barrido_calla_son_los_que_faltan_por_corregir() -> None:
    callados = [
        relativa
        for relativa, ruta in ARCHIVOS_DE_LA_APLICACION
        if not registro_anterior_en(relativa, ruta)
        and any(formas_en(texto) for _, texto in literales_de(ruta))
    ]

    assert callados == sorted({excepcion.archivo for excepcion in LO_QUE_FALTA_POR_CORREGIR})


def test_cada_excepcion_existe_dice_su_porque_y_de_verdad_dispara_el_detector() -> None:
    for excepcion in LO_QUE_FALTA_POR_CORREGIR:
        ruta = APLICACION / excepcion.archivo

        assert ruta.is_file(), excepcion.archivo
        assert excepcion.texto in ruta.read_text(encoding="utf-8"), excepcion.texto
        assert formas_en(excepcion.texto) != [], excepcion.texto
        assert len(excepcion.porque) > 40, excepcion.archivo


def test_la_excepcion_solo_tapa_su_propio_texto_en_su_propio_archivo() -> None:
    assert sin_lo_permitido("Usa una URL como ésta", ["Usa una URL como"]) == " ésta"
    assert formas_en(sin_lo_permitido("Usa una URL como. Revisa", ["Usa una URL como"])) == [
        "revisa"
    ]
    assert formas_en("Usa una URL y Revisa") == ["usa"]
    assert registro_anterior_en("otro/modulo.py", APLICACION / "core/cors.py") != []


def test_el_imperativo_solo_cuenta_cuando_abre_la_oracion() -> None:
    assert formas_en("Revisa las fechas del periodo.") == ["revisa"]
    assert formas_en("Quien revisa el seguimiento es la Dirección.") == []
    assert formas_en("La carga del archivo no se completó.") == []
    assert formas_en("Ya existe una captura para el indicador.") == []
    assert formas_en("El periodo cerró. Revise las dos fechas.") == []
    assert formas_en("El periodo cerró. Revisa las dos fechas.") == ["revisa"]


def test_el_barrido_no_cuenta_los_docstrings_ni_el_codigo() -> None:
    fuente = APLICACION / "modules/poa_planning/application/access_control.py"
    textos = [texto for _, texto in literales_de(fuente)]

    assert all("Quién puede escribir en el seguimiento" not in texto for texto in textos)
    assert "Esta operación requiere permisos de Planeación." in textos


EL_NOMBRE_DESARROLLADO = (
    (
        "poa_planning.EL_EJERCICIO_POA_NO_EXISTE",
        EL_EJERCICIO_POA_NO_EXISTE,
        "El ejercicio del Programa Operativo Anual no existe.",
    ),
    (
        "EL_AREA_NO_EXISTE",
        EL_AREA_NO_EXISTE,
        "El área no existe. Revise el catálogo de áreas antes de continuar.",
    ),
    (
        "EL_AREA_YA_TIENE_SU_POA",
        EL_AREA_YA_TIENE_SU_POA,
        "El área ya tiene su Programa Operativo Anual en este ejercicio.",
    ),
    (
        "EL_POA_DEL_AREA_NO_EXISTE",
        EL_POA_DEL_AREA_NO_EXISTE,
        "El Programa Operativo Anual del área no existe.",
    ),
    (
        "LO_MOVIERON_AL_ENVIAR",
        LO_MOVIERON_AL_ENVIAR,
        "El Programa Operativo Anual del área fue modificado por otra solicitud. Vuelva a "
        "consultarlo antes de presentarlo.",
    ),
    (
        "LA_ACTIVIDAD_LA_MOVIERON",
        LA_ACTIVIDAD_LA_MOVIERON,
        "La actividad fue modificada por otra solicitud. Vuelva a consultarla antes de guardar.",
    ),
    (
        "EL_SEGUIMIENTO_NO_ES_DEL_AREA",
        EL_SEGUIMIENTO_NO_ES_DEL_AREA,
        "El seguimiento del Programa Operativo Anual no corresponde al área de la cuenta.",
    ),
)


@pytest.mark.parametrize(("nombre", "dicho", "esperado"), EL_NOMBRE_DESARROLLADO)
def test_los_mensajes_corregidos_desarrollan_el_nombre_institucional(
    nombre: str, dicho: str, esperado: str
) -> None:
    assert dicho == esperado, nombre
    assert "POA" not in dicho, nombre


def test_el_mensaje_del_ejercicio_se_dice_una_sola_vez_en_todo_el_backend() -> None:
    sueltos = [
        f"{relativa}:{linea}"
        for relativa, ruta in ARCHIVOS_DE_LA_APLICACION
        for linea, texto in literales_de(ruta)
        if "ejercicio POA no existe" in texto
        or "ejercicio del Programa Operativo Anual no existe" in texto
    ]

    assert sueltos == ["modules/poa_planning/domain/entities.py:13"]


def _campos_en_el_registro_anterior() -> list[str]:
    anteriores = []
    for ruta in sorted(PLANTILLAS_DE_CORREO.glob("*.json")):
        contenido = json.loads(ruta.read_text(encoding="utf-8"))["contenido"]
        anteriores.extend(
            f"{ruta.stem}.{campo}" for campo in CAMPOS_DEL_CORREO if formas_en(contenido[campo])
        )
    return anteriores


def test_los_mensajes_de_correo_siguen_en_el_registro_anterior_y_su_cuenta_esta_escrita() -> None:
    plantillas = sorted(PLANTILLAS_DE_CORREO.glob("*.json"))
    anteriores = _campos_en_el_registro_anterior()

    assert len(plantillas) == PLANTILLAS_DE_CORREO_QUE_HAY
    assert len({nombre.split(".")[0] for nombre in anteriores}) == (
        PLANTILLAS_EN_EL_REGISTRO_ANTERIOR
    )
    assert len(anteriores) == CAMPOS_EN_EL_REGISTRO_ANTERIOR
