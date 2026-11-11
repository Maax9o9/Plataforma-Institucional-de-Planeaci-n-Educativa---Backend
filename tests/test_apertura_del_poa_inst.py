from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.modules.poa_institucional.api.schemas import AperturaDelPoaRespuesta
from app.modules.poa_institucional.application.use_cases.manage_poa_area import (
    OpenedPoa,
    OpenInstitutionalPoa,
    OpenInstitutionalPoaCommand,
    PoaAreaWithWindow,
    ReopenPoaArea,
    ReopenPoaAreaCommand,
    SaveActivityCommand,
    SubmitPoaAreaCommand,
)
from app.modules.poa_institucional.domain.entities import (
    EL_AREA_NO_EXISTE,
    LO_MOVIERON_AL_REABRIR,
    CaptureWindow,
    EstadoDelRegistro,
    PoaArea,
    PoaAreaStatus,
    dias_naturales_restantes,
    ensure_capture_is_open,
    estado_del_registro,
)
from app.modules.poa_planning.domain.entities import EL_EJERCICIO_POA_NO_EXISTE
from app.shared.domain.calendar import el_dia_en_letras
from app.shared.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ResourceNotFoundError,
    ValidationError,
)
from test_poa_del_area import (
    DOCE_METAS_DESIGUALES_QUE_SUMAN_24,
    Tablero,
    _tablero_en_memoria,
    _tablero_en_postgresql,
)

#: El codigo del repositorio no lleva invisibles literales -lo comprueba
#: `test_el_codigo_tampoco_trae_los_invisibles_que_el_dominio_quita`-, asi
#: que el que estas pruebas mandan como motivo se escribe con su escape.
ESPACIO_DE_ANCHO_CERO = "\u200b"

HOY = date(2026, 11, 1)

DEL_1_AL_30_DE_NOVIEMBRE = (date(2026, 11, 1), date(2026, 11, 30))

MESES_EN_LETRAS = {
    1: "1 de enero de 2026",
    2: "2 de febrero de 2026",
    3: "3 de marzo de 2026",
    4: "4 de abril de 2026",
    5: "5 de mayo de 2026",
    6: "6 de junio de 2026",
    7: "7 de julio de 2026",
    8: "8 de agosto de 2026",
    9: "9 de septiembre de 2026",
    10: "10 de octubre de 2026",
    11: "11 de noviembre de 2026",
    12: "12 de diciembre de 2026",
}


@pytest.fixture(params=["memoria", "postgresql"])
async def tablero(request):
    if request.param == "memoria":
        yield _tablero_en_memoria()
    else:
        async with _tablero_en_postgresql() as en_postgresql:
            yield en_postgresql


def _ventana(
    desde: date = DEL_1_AL_30_DE_NOVIEMBRE[0],
    hasta: date = DEL_1_AL_30_DE_NOVIEMBRE[1],
    **campos,
) -> CaptureWindow:
    return CaptureWindow(opens_on=desde, closes_on=hasta, **campos)


def _abrir(tablero: Tablero, *, hoy: date = HOY) -> OpenInstitutionalPoa:
    return OpenInstitutionalPoa(tablero.repo, tablero.ejercicios, tablero.areas)


def _reabrir(tablero: Tablero) -> ReopenPoaArea:
    return ReopenPoaArea(tablero.repo, tablero.areas)


def _guardar(tablero: Tablero, *, hoy: date = HOY):
    from app.modules.poa_institucional.application.use_cases.manage_poa_area import SavePoaActivity

    return SavePoaActivity(tablero.repo, tablero.arbol, tablero.areas, today=lambda: hoy)


def _enviar(tablero: Tablero, *, hoy: date = HOY):
    from app.modules.poa_institucional.application.use_cases.manage_poa_area import SubmitPoaArea

    return SubmitPoaArea(tablero.repo, tablero.liderazgo, tablero.areas, today=lambda: hoy)


async def _un_poa_abierto(
    tablero: Tablero,
    *,
    desde: date = DEL_1_AL_30_DE_NOVIEMBRE[0],
    hasta: date = DEL_1_AL_30_DE_NOVIEMBRE[1],
    con_responsable: bool = True,
):
    area = await tablero.nueva_area()
    if con_responsable:
        await tablero.dar_responsable(area)
    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=await tablero.nuevo_ejercicio(),
            area_ids=[area],
            opens_on=desde,
            closes_on=hasta,
        )
    )
    return abierto.opened[0]


async def _actividad_completa(tablero: Tablero, poa_area, **campos):
    from app.modules.poa_institucional.domain.entities import MonthlyTarget

    return await _guardar(tablero).execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            name="Impartir el taller de titulación",
            node_id=await _nodo(tablero),
            unit_id=await tablero.nueva_unidad(),
            evaluation_method="Lista de asistencia",
            annual_target=sum(DOCE_METAS_DESIGUALES_QUE_SUMAN_24),
            monthly=[
                MonthlyTarget(month=mes, target=DOCE_METAS_DESIGUALES_QUE_SUMAN_24[mes - 1])
                for mes in range(1, 13)
            ],
            **campos,
        )
    )


async def _nodo(tablero: Tablero) -> int:
    from uuid import uuid4

    from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
        NodeKind,
        StrategicNode,
    )

    nodo = StrategicNode(
        version_id=await tablero.nueva_version(),
        parent_id=None,
        kind=NodeKind.ACCION,
        key=f"accion-{uuid4().hex[:8]}",
        name="Una acción del PIDE",
        order=1,
    )
    await tablero.arbol.add(nodo)
    return nodo.id


@pytest.mark.parametrize("mes", sorted(MESES_EN_LETRAS))
def test_un_dia_se_dice_con_el_mes_en_letras_y_sin_cero_delante(mes):
    assert el_dia_en_letras(date(2026, mes, mes)) == MESES_EN_LETRAS[mes]


def test_el_primer_dia_de_la_ventana_esta_dentro():
    assert _ventana().includes(date(2026, 11, 1)) is True


def test_el_ultimo_dia_de_la_ventana_esta_dentro():
    assert _ventana().includes(date(2026, 11, 30)) is True


def test_el_dia_anterior_al_primero_esta_fuera():
    assert _ventana().includes(date(2026, 10, 31)) is False


def test_el_dia_siguiente_al_ultimo_esta_fuera():
    assert _ventana().includes(date(2026, 12, 1)) is False


def test_una_ventana_de_un_solo_dia_incluye_ese_dia():
    de_un_dia = _ventana(date(2026, 11, 30), date(2026, 11, 30))

    assert [
        de_un_dia.includes(date(2026, 11, 29)),
        de_un_dia.includes(date(2026, 11, 30)),
        de_un_dia.includes(date(2026, 12, 1)),
    ] == [False, True, False]


@pytest.mark.parametrize(
    ("dia", "esperado"),
    [
        (date(2026, 10, 31), EstadoDelRegistro.POR_INICIAR),
        (date(2026, 11, 1), EstadoDelRegistro.ABIERTO),
        (date(2026, 11, 15), EstadoDelRegistro.ABIERTO),
        (date(2026, 11, 30), EstadoDelRegistro.ABIERTO),
        (date(2026, 12, 1), EstadoDelRegistro.CONCLUIDO),
    ],
)
def test_el_motivo_distingue_el_periodo_por_iniciar_del_ya_concluido(dia, esperado):
    assert estado_del_registro(_ventana(), today=dia) is esperado


def test_sin_ningun_periodo_el_motivo_es_que_nunca_se_habilito():
    assert estado_del_registro(None, today=HOY) is EstadoDelRegistro.SIN_HABILITAR


def test_el_motivo_de_una_ventana_de_un_solo_dia_cambia_en_sus_dos_bordes():
    de_un_dia = _ventana(date(2026, 11, 30), date(2026, 11, 30))

    assert [
        estado_del_registro(de_un_dia, today=date(2026, 11, 29)),
        estado_del_registro(de_un_dia, today=date(2026, 11, 30)),
        estado_del_registro(de_un_dia, today=date(2026, 12, 1)),
    ] == [
        EstadoDelRegistro.POR_INICIAR,
        EstadoDelRegistro.ABIERTO,
        EstadoDelRegistro.CONCLUIDO,
    ]


@pytest.mark.parametrize(
    ("dia", "esperado"),
    [
        (date(2026, 11, 1), 29),
        (date(2026, 11, 15), 15),
        (date(2026, 11, 29), 1),
        (date(2026, 11, 30), 0),
    ],
)
def test_los_dias_restantes_se_cuentan_desde_el_dia_institucional(dia, esperado):
    assert dias_naturales_restantes(_ventana(), today=dia) == esperado


@pytest.mark.parametrize("dia", [date(2026, 10, 31), date(2026, 12, 1)])
def test_fuera_del_periodo_no_hay_dias_restantes_que_mostrar(dia):
    assert dias_naturales_restantes(_ventana(), today=dia) is None


def test_sin_ningun_periodo_no_hay_dias_restantes_que_mostrar():
    assert dias_naturales_restantes(None, today=HOY) is None


def test_el_total_de_avisados_cuenta_solo_lo_que_la_apertura_abrio():
    ventana = _ventana()
    recien = PoaAreaWithWindow(
        poa_area=PoaArea(id=1, exercise_id=7, area_id=11), window=ventana, avisados=2
    )
    de_antes = PoaAreaWithWindow(
        poa_area=PoaArea(id=2, exercise_id=7, area_id=12), window=ventana, avisados=5
    )

    respuesta = AperturaDelPoaRespuesta.from_domain(
        7, OpenedPoa(opened=[recien], already_open=[de_antes])
    )

    assert respuesta.avisados == 2
    assert respuesta.areas_sin_a_quien_avisar == []


def test_el_area_sin_a_quien_avisar_sale_en_la_lista_y_la_que_no_se_pudo_medir_no():
    ventana = _ventana()
    sin_nadie = PoaAreaWithWindow(
        poa_area=PoaArea(id=1, exercise_id=7, area_id=11), window=ventana, avisados=0
    )
    sin_medir = PoaAreaWithWindow(
        poa_area=PoaArea(id=2, exercise_id=7, area_id=12), window=ventana, avisados=None
    )

    respuesta = AperturaDelPoaRespuesta.from_domain(7, OpenedPoa(opened=[sin_nadie, sin_medir]))

    assert respuesta.avisados == 0
    assert respuesta.areas_sin_a_quien_avisar == [11]


def test_una_ventana_que_cierra_antes_de_abrir_se_rechaza_diciendo_las_dos_fechas():
    with pytest.raises(ValidationError) as caido:
        _ventana(date(2026, 11, 30), date(2026, 11, 29)).validate()

    assert "30 de noviembre de 2026" in str(caido.value)
    assert "29 de noviembre de 2026" in str(caido.value)


def test_una_ventana_que_abre_y_cierra_el_mismo_dia_se_acepta():
    _ventana(date(2026, 11, 30), date(2026, 11, 30)).validate()


@pytest.mark.parametrize("numero", [0, -1])
def test_una_apertura_numerada_por_debajo_de_uno_se_rechaza(numero):
    with pytest.raises(ValidationError):
        _ventana(number=numero, reason="Un motivo").validate()


def test_la_primera_apertura_no_pide_motivo():
    _ventana(number=1).validate()


@pytest.mark.parametrize("motivo", [None, "", "   ", ESPACIO_DE_ANCHO_CERO])
def test_un_periodo_nuevo_sin_motivo_se_rechaza(motivo):
    with pytest.raises(ValidationError) as caido:
        _ventana(number=2, reason=motivo).validate()

    assert "requiere un motivo" in str(caido.value)


def test_el_motivo_del_periodo_nuevo_se_guarda_recortado():
    ventana = _ventana(number=2, reason="  El área no entregó  ")

    ventana.validate()

    assert ventana.reason == "El área no entregó"


def test_dentro_de_la_ventana_no_bloquea_ni_el_primer_ni_el_ultimo_dia():
    for dia in (date(2026, 11, 1), date(2026, 11, 15), date(2026, 11, 30)):
        ensure_capture_is_open(_ventana(), area_name="Ingeniería Biomédica", today=dia)


def test_pasada_la_fecha_de_cierre_el_mensaje_dice_la_fecha_y_que_solicite_otro_periodo():
    with pytest.raises(InvalidStateError) as caido:
        ensure_capture_is_open(
            _ventana(), area_name="Ingeniería Biomédica", today=date(2026, 12, 1)
        )

    assert str(caido.value) == (
        "El periodo de captura del Programa Operativo Anual de Ingeniería Biomédica "
        "concluyó el 30 de noviembre de 2026. Solicite a la Dirección de Planeación que "
        "habilite un nuevo periodo."
    )


def test_antes_de_la_fecha_de_apertura_el_mensaje_dice_desde_cuando_se_podra():
    with pytest.raises(InvalidStateError) as caido:
        ensure_capture_is_open(
            _ventana(), area_name="Ingeniería Biomédica", today=date(2026, 10, 31)
        )

    assert str(caido.value) == (
        "El periodo de captura del Programa Operativo Anual de Ingeniería Biomédica inicia "
        "el 1 de noviembre de 2026. Podrá registrar sus actividades a partir de esa fecha."
    )


def test_un_poa_sin_ningun_periodo_dice_que_planeacion_debe_habilitarlo():
    with pytest.raises(InvalidStateError) as caido:
        ensure_capture_is_open(None, area_name="Ingeniería Biomédica", today=HOY)

    assert str(caido.value) == (
        "El área de Ingeniería Biomédica todavía no tiene habilitado el registro de "
        "actividades en este ejercicio. La Dirección de Planeación debe habilitarlo antes de "
        "que pueda capturarse."
    )


def test_sin_el_nombre_del_area_el_mensaje_sigue_siendo_una_frase():
    with pytest.raises(InvalidStateError) as caido:
        ensure_capture_is_open(_ventana(), area_name=None, today=date(2026, 12, 1))

    assert str(caido.value) == (
        "El periodo de captura del Programa Operativo Anual concluyó el 30 de noviembre de "
        "2026. Solicite a la Dirección de Planeación que habilite un nuevo periodo."
    )


async def test_abrir_para_las_areas_elegidas_les_deja_su_ventana_y_quien_la_abrio(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    unas = sorted([await tablero.nueva_area(), await tablero.nueva_area()])
    quien = await tablero.nuevo_usuario(unas[0], None)

    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=unas,
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
            opened_by=quien,
        )
    )

    assert [uno.poa_area.area_id for uno in abierto.opened] == unas
    assert abierto.already_open == []
    for uno in abierto.opened:
        assert uno.poa_area.status is PoaAreaStatus.BORRADOR
        assert (uno.window.number, uno.window.opens_on, uno.window.closes_on) == (
            1,
            date(2026, 11, 1),
            date(2026, 11, 30),
        )
        assert uno.window.opened_by == quien
        assert uno.window.reason is None


async def test_abrir_para_todas_abre_las_areas_activas_y_ninguna_retirada(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    activa = await tablero.nueva_area()
    retirada = await tablero.nueva_area()
    jubilada = await tablero.areas.get_by_id(retirada)
    jubilada.is_active = False
    await tablero.areas.update(jubilada)

    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=None,
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    abiertas = {uno.poa_area.area_id for uno in abierto.opened}
    assert abiertas == {area.id for area in await tablero.areas.list(active_only=True)}
    assert activa in abiertas
    assert retirada not in abiertas


async def test_abrir_para_todas_incluye_al_area_de_quien_abre(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    planeacion = await tablero.nueva_area()
    quien = await tablero.nuevo_usuario(planeacion, "planeacion")

    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=None,
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
            opened_by=quien,
        )
    )

    assert planeacion in {uno.poa_area.area_id for uno in abierto.opened}


async def test_abrir_dos_veces_no_duplica_ni_cambia_la_ventana_y_dice_que_ya_estaba(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.nueva_area()
    primera = OpenInstitutionalPoaCommand(
        exercise_id=ejercicio,
        area_ids=[area],
        opens_on=date(2026, 11, 1),
        closes_on=date(2026, 11, 30),
    )
    abierto = await _abrir(tablero).execute(primera)

    otra_vez = await _abrir(tablero).execute(
        replace(primera, opens_on=date(2027, 1, 1), closes_on=date(2027, 1, 31))
    )

    assert otra_vez.opened == []
    assert [uno.poa_area.id for uno in otra_vez.already_open] == [abierto.opened[0].poa_area.id]
    sigue = otra_vez.already_open[0].window
    assert (sigue.number, sigue.opens_on, sigue.closes_on) == (
        1,
        date(2026, 11, 1),
        date(2026, 11, 30),
    )


async def test_abrir_reparte_entre_lo_que_se_abrio_y_lo_que_ya_estaba(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    ya_estaba = await tablero.nueva_area()
    nueva = await tablero.nueva_area()
    await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=[ya_estaba],
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    segunda = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=[nueva, ya_estaba],
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    assert [uno.poa_area.area_id for uno in segunda.opened] == [nueva]
    assert [uno.poa_area.area_id for uno in segunda.already_open] == [ya_estaba]


async def test_abrir_dos_veces_la_misma_area_en_la_misma_llamada_la_abre_una_sola_vez(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.nueva_area()

    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=[area, area, area],
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    assert [uno.poa_area.area_id for uno in abierto.opened] == [area]


async def test_abrir_un_ejercicio_que_no_existe_no_abre_nada(tablero):
    area = await tablero.nueva_area()

    with pytest.raises(ValidationError, match=EL_EJERCICIO_POA_NO_EXISTE):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=10**9,
                area_ids=[area],
                opens_on=date(2026, 11, 1),
                closes_on=date(2026, 11, 30),
            )
        )

    assert await tablero.repo.find_poa_area(10**9, area) is None


async def test_abrir_para_un_area_que_no_existe_no_abre_ninguna_de_la_lista(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    buena = await tablero.nueva_area()

    with pytest.raises(ValidationError, match=EL_AREA_NO_EXISTE):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=ejercicio,
                area_ids=[buena, 10**9],
                opens_on=date(2026, 11, 1),
                closes_on=date(2026, 11, 30),
            )
        )

    assert await tablero.repo.find_poa_area(ejercicio, buena) is None


async def test_abrir_para_un_area_retirada_que_se_nombro_a_mano_se_niega(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    retirada = await tablero.nueva_area()
    jubilada = await tablero.areas.get_by_id(retirada)
    jubilada.is_active = False
    await tablero.areas.update(jubilada)

    with pytest.raises(ValidationError, match="retirada"):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=ejercicio,
                area_ids=[retirada],
                opens_on=date(2026, 11, 1),
                closes_on=date(2026, 11, 30),
            )
        )

    assert await tablero.repo.find_poa_area(ejercicio, retirada) is None


async def test_abrir_sin_elegir_ninguna_area_se_niega(tablero):
    ejercicio = await tablero.nuevo_ejercicio()

    with pytest.raises(ValidationError, match="al menos un área"):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=ejercicio,
                area_ids=[],
                opens_on=date(2026, 11, 1),
                closes_on=date(2026, 11, 30),
            )
        )


async def test_abrir_con_la_fecha_de_cierre_antes_de_la_de_apertura_no_abre_nada(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.nueva_area()

    with pytest.raises(ValidationError):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=ejercicio,
                area_ids=[area],
                opens_on=date(2026, 11, 30),
                closes_on=date(2026, 11, 29),
            )
        )

    assert await tablero.repo.find_poa_area(ejercicio, area) is None


async def test_abrir_devuelve_las_areas_en_orden_de_su_id_y_no_en_el_que_llegaron(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    unas = sorted([await tablero.nueva_area() for _ in range(4)])

    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=list(reversed(unas)),
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    assert [uno.poa_area.area_id for uno in abierto.opened] == unas


async def test_reabrir_deja_la_ventana_nueva_y_guarda_la_anterior(tablero):
    abierto = await _un_poa_abierto(tablero)

    reabierto = await _reabrir(tablero).execute(
        ReopenPoaAreaCommand(
            exercise_id=abierto.poa_area.exercise_id,
            area_id=abierto.poa_area.area_id,
            opens_on=date(2026, 12, 1),
            closes_on=date(2026, 12, 15),
            reason="El área no entregó en la fecha dispuesta",
        )
    )

    assert (reabierto.window.number, reabierto.window.opens_on, reabierto.window.closes_on) == (
        2,
        date(2026, 12, 1),
        date(2026, 12, 15),
    )
    historia = await tablero.repo.capture_windows(abierto.poa_area.id)
    assert [una.number for una in historia] == [1, 2]
    assert (historia[0].opens_on, historia[0].closes_on) == DEL_1_AL_30_DE_NOVIEMBRE


async def test_la_ventana_vigente_es_la_del_numero_mas_alto(tablero):
    abierto = await _un_poa_abierto(tablero)
    for cuantas in range(2, 5):
        await _reabrir(tablero).execute(
            ReopenPoaAreaCommand(
                exercise_id=abierto.poa_area.exercise_id,
                area_id=abierto.poa_area.area_id,
                opens_on=date(2026, 12, cuantas),
                closes_on=date(2026, 12, 20),
                reason=f"El periodo número {cuantas}",
            )
        )

    vigente = await tablero.repo.current_capture_window(abierto.poa_area.id)

    assert (vigente.number, vigente.opens_on, vigente.reason) == (
        4,
        date(2026, 12, 4),
        "El periodo número 4",
    )


async def test_reabrir_un_poa_enviado_lo_devuelve_a_borrador_y_avanza_su_version(tablero):
    abierto = await _un_poa_abierto(tablero)
    await _actividad_completa(tablero, abierto.poa_area)
    enviado = await _enviar(tablero).execute(
        SubmitPoaAreaCommand(poa_area_id=abierto.poa_area.id, version=abierto.poa_area.version)
    )

    reabierto = await _reabrir(tablero).execute(
        ReopenPoaAreaCommand(
            exercise_id=abierto.poa_area.exercise_id,
            area_id=abierto.poa_area.area_id,
            opens_on=date(2026, 12, 1),
            closes_on=date(2026, 12, 15),
            reason="El área tiene que corregir una actividad",
        )
    )

    guardado = await tablero.repo.get_poa_area(abierto.poa_area.id)
    assert enviado.status is PoaAreaStatus.ENVIADO
    assert reabierto.poa_area.status is PoaAreaStatus.BORRADOR
    assert guardado.status is PoaAreaStatus.BORRADOR
    assert guardado.version == enviado.version + 1


async def test_reabrir_un_poa_en_borrador_lo_deja_en_borrador_y_avanza_su_version(tablero):
    abierto = await _un_poa_abierto(tablero)

    await _reabrir(tablero).execute(
        ReopenPoaAreaCommand(
            exercise_id=abierto.poa_area.exercise_id,
            area_id=abierto.poa_area.area_id,
            opens_on=date(2026, 12, 1),
            closes_on=date(2026, 12, 15),
            reason="Se le dio más tiempo",
        )
    )

    guardado = await tablero.repo.get_poa_area(abierto.poa_area.id)
    assert guardado.status is PoaAreaStatus.BORRADOR
    assert guardado.version == abierto.poa_area.version + 1


@pytest.mark.parametrize("motivo", ["", "   ", ESPACIO_DE_ANCHO_CERO])
async def test_reabrir_sin_decir_por_que_se_niega_y_no_cambia_el_periodo(tablero, motivo):
    abierto = await _un_poa_abierto(tablero)

    with pytest.raises(ValidationError, match="requiere un motivo"):
        await _reabrir(tablero).execute(
            ReopenPoaAreaCommand(
                exercise_id=abierto.poa_area.exercise_id,
                area_id=abierto.poa_area.area_id,
                opens_on=date(2026, 12, 1),
                closes_on=date(2026, 12, 15),
                reason=motivo,
            )
        )

    vigente = await tablero.repo.current_capture_window(abierto.poa_area.id)
    assert (vigente.number, vigente.closes_on) == (1, DEL_1_AL_30_DE_NOVIEMBRE[1])


async def test_reabrir_lo_que_nadie_abrio_lo_dice_nombrando_el_area(tablero):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.areas.get_by_id(await tablero.nueva_area())

    with pytest.raises(ResourceNotFoundError) as caido:
        await _reabrir(tablero).execute(
            ReopenPoaAreaCommand(
                exercise_id=ejercicio,
                area_id=area.id,
                opens_on=date(2026, 12, 1),
                closes_on=date(2026, 12, 15),
                reason="Un motivo cualquiera",
            )
        )

    assert area.name in str(caido.value)
    assert "Ábralo" in str(caido.value)


async def test_reabrir_con_la_fecha_de_cierre_antes_de_la_de_apertura_se_niega(tablero):
    abierto = await _un_poa_abierto(tablero)

    with pytest.raises(ValidationError):
        await _reabrir(tablero).execute(
            ReopenPoaAreaCommand(
                exercise_id=abierto.poa_area.exercise_id,
                area_id=abierto.poa_area.area_id,
                opens_on=date(2026, 12, 15),
                closes_on=date(2026, 12, 1),
                reason="Un motivo cualquiera",
            )
        )

    vigente = await tablero.repo.current_capture_window(abierto.poa_area.id)
    assert vigente.number == 1


@pytest.mark.parametrize("dia", [DEL_1_AL_30_DE_NOVIEMBRE[0], DEL_1_AL_30_DE_NOVIEMBRE[1]])
async def test_registrar_una_actividad_el_primer_y_el_ultimo_dia_de_la_ventana_se_permite(
    tablero, dia
):
    abierto = await _un_poa_abierto(tablero)

    guardada = await _guardar(tablero, hoy=dia).execute(
        SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="Una actividad nueva")
    )

    assert guardada.id != 0


@pytest.mark.parametrize(
    "dia",
    [
        DEL_1_AL_30_DE_NOVIEMBRE[0] - timedelta(days=1),
        DEL_1_AL_30_DE_NOVIEMBRE[1] + timedelta(days=1),
    ],
)
async def test_registrar_una_actividad_fuera_de_la_ventana_se_bloquea(tablero, dia):
    abierto = await _un_poa_abierto(tablero)

    with pytest.raises(InvalidStateError):
        await _guardar(tablero, hoy=dia).execute(
            SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="Una actividad nueva")
        )

    assert await tablero.repo.list_activities(abierto.poa_area.id) == []


async def test_el_mensaje_del_bloqueo_nombra_el_area_y_la_fecha_de_cierre(tablero):
    abierto = await _un_poa_abierto(tablero)
    area = await tablero.areas.get_by_id(abierto.poa_area.area_id)

    with pytest.raises(InvalidStateError) as caido:
        await _guardar(tablero, hoy=date(2026, 12, 1)).execute(
            SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="Una actividad nueva")
        )

    assert str(caido.value) == (
        f"El periodo de captura del Programa Operativo Anual de {area.name} concluyó el "
        "30 de noviembre de 2026. Solicite a la Dirección de Planeación que habilite un nuevo "
        "periodo."
    )


async def test_corregir_una_actividad_fuera_de_la_ventana_se_bloquea(tablero):
    abierto = await _un_poa_abierto(tablero)
    guardada = await _guardar(tablero).execute(
        SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="La que ya estaba")
    )

    with pytest.raises(InvalidStateError):
        await _guardar(tablero, hoy=date(2026, 12, 1)).execute(
            SaveActivityCommand(
                poa_area_id=abierto.poa_area.id,
                activity_id=guardada.id,
                version=guardada.version,
                name="Corregida fuera de plazo",
            )
        )

    assert (await tablero.repo.get_activity(guardada.id)).name == "La que ya estaba"


async def test_presentar_fuera_de_la_ventana_se_bloquea(tablero):
    abierto = await _un_poa_abierto(tablero)
    await _actividad_completa(tablero, abierto.poa_area)

    with pytest.raises(InvalidStateError):
        await _enviar(tablero, hoy=date(2026, 12, 1)).execute(
            SubmitPoaAreaCommand(poa_area_id=abierto.poa_area.id, version=abierto.poa_area.version)
        )

    assert (await tablero.repo.get_poa_area(abierto.poa_area.id)).status is PoaAreaStatus.BORRADOR


async def test_un_poa_cerrado_se_sigue_leyendo_igual(tablero):
    abierto = await _un_poa_abierto(tablero)
    guardada = await _guardar(tablero).execute(
        SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="La que se capturó a tiempo")
    )

    leido = await tablero.repo.get_poa_area(abierto.poa_area.id)
    actividades = await tablero.repo.list_activities(abierto.poa_area.id)
    una = await tablero.repo.get_activity(guardada.id)

    assert leido.id == abierto.poa_area.id
    assert [actividad.name for actividad in actividades] == ["La que se capturó a tiempo"]
    assert una.name == "La que se capturó a tiempo"


async def test_tras_reabrir_con_una_ventana_que_incluye_hoy_se_vuelve_a_capturar(tablero):
    abierto = await _un_poa_abierto(tablero, desde=date(2026, 1, 1), hasta=date(2026, 1, 31))
    with pytest.raises(InvalidStateError):
        await _guardar(tablero).execute(
            SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="La que no cupo")
        )

    await _reabrir(tablero).execute(
        ReopenPoaAreaCommand(
            exercise_id=abierto.poa_area.exercise_id,
            area_id=abierto.poa_area.area_id,
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
            reason="El área no entregó en enero",
        )
    )
    guardada = await _guardar(tablero).execute(
        SaveActivityCommand(poa_area_id=abierto.poa_area.id, name="La que ya cabe")
    )

    assert guardada.name == "La que ya cabe"


async def test_el_bloqueo_dice_lo_mismo_en_memoria_que_en_postgresql():
    mensajes = []
    async with _tablero_en_postgresql() as en_postgresql:
        for tablero, nombre in ((_tablero_en_memoria(), "memoria"), (en_postgresql, "postgresql")):
            area_id = await tablero.nueva_area()
            area = await tablero.areas.get_by_id(area_id)
            area.name = "Ingeniería Biomédica"
            await tablero.areas.update(area)
            abierto = await _abrir(tablero).execute(
                OpenInstitutionalPoaCommand(
                    exercise_id=await tablero.nuevo_ejercicio(),
                    area_ids=[area_id],
                    opens_on=date(2026, 11, 1),
                    closes_on=date(2026, 11, 30),
                )
            )
            with pytest.raises(InvalidStateError) as caido:
                await _guardar(tablero, hoy=date(2026, 12, 1)).execute(
                    SaveActivityCommand(
                        poa_area_id=abierto.opened[0].poa_area.id, name="Fuera de plazo"
                    )
                )
            mensajes.append((nombre, str(caido.value)))

    assert mensajes[0][1] == mensajes[1][1]
    assert mensajes[0][1] == (
        "El periodo de captura del Programa Operativo Anual de Ingeniería Biomédica "
        "concluyó el 30 de noviembre de 2026. Solicite a la Dirección de Planeación que "
        "habilite un nuevo periodo."
    )


async def test_la_historia_de_las_aperturas_es_la_misma_en_memoria_que_en_postgresql():
    historias = []
    async with _tablero_en_postgresql() as en_postgresql:
        for tablero in (_tablero_en_memoria(), en_postgresql):
            abierto = await _un_poa_abierto(tablero)
            for cuantas in (2, 3):
                await _reabrir(tablero).execute(
                    ReopenPoaAreaCommand(
                        exercise_id=abierto.poa_area.exercise_id,
                        area_id=abierto.poa_area.area_id,
                        opens_on=date(2026, 12, cuantas),
                        closes_on=date(2026, 12, 31),
                        reason=f"El periodo número {cuantas}",
                    )
                )
            historias.append(
                [
                    (una.number, una.opens_on, una.closes_on, una.reason)
                    for una in await tablero.repo.capture_windows(abierto.poa_area.id)
                ]
            )

    assert historias[0] == historias[1]
    assert historias[0] == [
        (1, date(2026, 11, 1), date(2026, 11, 30), None),
        (2, date(2026, 12, 2), date(2026, 12, 31), "El periodo número 2"),
        (3, date(2026, 12, 3), date(2026, 12, 31), "El periodo número 3"),
    ]


async def test_reabrir_sobre_una_version_vieja_no_pisa_el_cambio_ajeno(tablero):
    abierto = await _un_poa_abierto(tablero)
    await tablero.repo.save_poa_area_if_version_matches(
        replace(abierto.poa_area, status=PoaAreaStatus.BORRADOR)
    )
    anticuado = ReopenPoaArea(_RepoConVersionVieja(tablero.repo), tablero.areas)

    with pytest.raises(ConflictError) as caido:
        await anticuado.execute(
            ReopenPoaAreaCommand(
                exercise_id=abierto.poa_area.exercise_id,
                area_id=abierto.poa_area.area_id,
                opens_on=date(2026, 12, 1),
                closes_on=date(2026, 12, 15),
                reason="Un motivo cualquiera",
            )
        )

    assert str(caido.value) == LO_MOVIERON_AL_REABRIR
    vigente = await tablero.repo.current_capture_window(abierto.poa_area.id)
    assert vigente.number == 1


class _RepoConVersionVieja:
    def __init__(self, real) -> None:
        self.real = real

    def __getattr__(self, nombre):
        return getattr(self.real, nombre)

    async def find_poa_area(self, exercise_id: int, area_id: int):
        guardado = await self.real.find_poa_area(exercise_id, area_id)
        return None if guardado is None else replace(guardado, version=guardado.version - 1)


async def test_abrir_con_fechas_invalidas_se_niega_aunque_todas_las_areas_ya_estuvieran_abiertas(
    tablero,
):
    ejercicio = await tablero.nuevo_ejercicio()
    area = await tablero.nueva_area()
    await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio,
            area_ids=[area],
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
        )
    )

    with pytest.raises(ValidationError, match="Revise las dos fechas"):
        await _abrir(tablero).execute(
            OpenInstitutionalPoaCommand(
                exercise_id=ejercicio,
                area_ids=[area],
                opens_on=date(2026, 11, 30),
                closes_on=date(2026, 11, 29),
            )
        )


def test_el_reloj_de_los_casos_de_uso_es_el_del_calendario_institucional():
    from app.modules.poa_institucional.application.use_cases.manage_poa_area import (
        SavePoaActivity,
        SubmitPoaArea,
    )
    from app.shared.domain.calendar import institutional_today

    guardar = SavePoaActivity(None, None, None)
    enviar = SubmitPoaArea(None, None, None)

    assert guardar.today is institutional_today
    assert enviar.today is institutional_today


async def test_la_historia_guarda_quien_autorizo_cada_periodo(tablero):
    area = await tablero.nueva_area()
    quien_abrio = await tablero.nuevo_usuario(area, None)
    quien_reabrio = await tablero.nuevo_usuario(area, None)
    abierto = await _abrir(tablero).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=await tablero.nuevo_ejercicio(),
            area_ids=[area],
            opens_on=date(2026, 11, 1),
            closes_on=date(2026, 11, 30),
            opened_by=quien_abrio,
        )
    )

    await _reabrir(tablero).execute(
        ReopenPoaAreaCommand(
            exercise_id=abierto.opened[0].poa_area.exercise_id,
            area_id=area,
            opens_on=date(2026, 12, 1),
            closes_on=date(2026, 12, 15),
            reason="El área no entregó en la fecha dispuesta",
            opened_by=quien_reabrio,
        )
    )

    historia = await tablero.repo.capture_windows(abierto.opened[0].poa_area.id)
    assert [(una.number, una.opened_by) for una in historia] == [
        (1, quien_abrio),
        (2, quien_reabrio),
    ]
