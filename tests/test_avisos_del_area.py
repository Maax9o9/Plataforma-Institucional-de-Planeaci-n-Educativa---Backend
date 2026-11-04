from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

import pytest

from app.modules.identity_access.domain.entities import User
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.repository import InMemoryUserRepository
from app.modules.institutional_catalogs.domain.entities import Area
from app.modules.institutional_catalogs.infrastructure.repository import InMemoryAreaRepository
from app.modules.notifications.application.area_notices import (
    AVISO_DE_LA_APERTURA,
    AVISO_DE_PLANEACION,
    EL_AREA_DEL_AVISO_NO_EXISTE,
    ELIJA_AL_MENOS_UN_AREA_PARA_EL_AVISO,
    ESCRIBA_EL_MENSAJE_DEL_AVISO,
    ESCRIBA_EL_TITULO_DEL_AVISO,
    LA_ENTIDAD_DEL_AREA,
    LA_ENTIDAD_DEL_POA_DEL_AREA,
    NO_HAY_NINGUNA_AREA_EN_SERVICIO_QUE_AVISAR,
    TITULO_DE_LA_APERTURA,
    AreaNotices,
    AvisoEntregado,
    el_aviso_de_la_apertura,
)
from app.modules.poa_institucional.application.use_cases.manage_poa_area import (
    OpenInstitutionalPoa,
    OpenInstitutionalPoaCommand,
    ReopenPoaArea,
    ReopenPoaAreaCommand,
)
from app.modules.poa_planning.application.access_control import (
    can_be_told_the_area_poa_opened,
    can_capture_activity,
)
from app.modules.poa_planning.application.period_recipients import PoaPeriodRecipients
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ValidationError
from app.shared.domain.value_objects import Email
from test_poa_del_area import _tablero_en_memoria

ESPACIO_DE_ANCHO_CERO = chr(0x200B)

DEL_3_AL_30_DE_NOVIEMBRE = (date(2026, 11, 3), date(2026, 11, 30))

EL_AREA = 7
OTRA_AREA = 8


def _actor(rol: str | None, area_id: int | None = EL_AREA, *roles: str) -> ActorContext:
    nombrados = frozenset(() if rol is None else {rol, *roles})
    return ActorContext(id=1, roles=nombrados, area_id=area_id)


@dataclass
class ServicioQueAnota:
    avisados: list[dict] = field(default_factory=list)

    async def notify_user(self, **valores):
        self.avisados.append(valores)
        return None


@dataclass
class ServicioQueSeCae:
    intentos: int = 0

    async def notify_user(self, **valores):
        self.intentos += 1
        raise RuntimeError("El riel de notificaciones no contesta")


@dataclass
class AvisosQueAnotan:
    aperturas: list[dict] = field(default_factory=list)

    async def el_poa_del_area_se_abrio(self, **valores):
        self.aperturas.append(valores)
        return None


@dataclass
class AvisosQueSeCaen:
    intentos: int = 0

    async def el_poa_del_area_se_abrio(self, **valores):
        self.intentos += 1
        raise RuntimeError("El riel de notificaciones no contesta")


async def _las_areas(*ids: int) -> InMemoryAreaRepository:
    areas = InMemoryAreaRepository()
    for identificador in ids:
        area = Area.create(code=f"PRUEBA-{identificador}", name=f"Área número {identificador}")
        area.id = identificador
        await areas.add(area)
    return areas


async def _los_usuarios(*cuentas: tuple[int, set[str], bool]) -> InMemoryUserRepository:
    usuarios = InMemoryUserRepository()
    for area_id, roles, activo in cuentas:
        await usuarios.add(
            User(
                email=Email(f"persona-{uuid4().hex}@upchiapas.edu.mx"),
                full_name="Persona de prueba",
                password_hash="$argon2id$de$prueba",
                roles=frozenset(Role(rol) for rol in roles),
                area_id=area_id,
                is_active=activo,
            )
        )
    return usuarios


def _destinatarios(usuarios: InMemoryUserRepository) -> PoaPeriodRecipients:
    return PoaPeriodRecipients(forms=None, users=usuarios)


async def _avisos(usuarios: InMemoryUserRepository, servicio, *areas: int) -> AreaNotices:
    return AreaNotices(_destinatarios(usuarios), servicio, await _las_areas(*areas))


# ── El veredicto sobre `can_capture_activity` ────────────────────────────────


def test_el_permiso_de_captura_no_admite_al_responsable_del_area():
    assert can_capture_activity(_actor(Role.RESPONSABLE_AREA.value), EL_AREA) is False


def test_el_responsable_del_area_si_se_entera_de_que_su_poa_se_abrio():
    assert can_be_told_the_area_poa_opened(_actor(Role.RESPONSABLE_AREA.value), EL_AREA) is True


@pytest.mark.parametrize(
    "rol",
    [
        Role.CAPTURISTA_POA.value,
        Role.RESPONSABLE_AREA.value,
        Role.PLANEACION.value,
        Role.PLANEACION_ADMIN.value,
        Role.ADMIN_SISTEMA.value,
    ],
)
def test_quien_formula_o_encabeza_el_area_se_entera_de_la_apertura(rol):
    assert can_be_told_the_area_poa_opened(_actor(rol), EL_AREA) is True


@pytest.mark.parametrize("rol", [Role.CONSULTA.value, Role.RECTORIA.value, Role.REVISOR_POA.value])
def test_quien_solo_consulta_o_revisa_no_se_entera_de_la_apertura(rol):
    assert can_be_told_the_area_poa_opened(_actor(rol), EL_AREA) is False


@pytest.mark.parametrize(
    "rol",
    [
        Role.CAPTURISTA_POA.value,
        Role.RESPONSABLE_AREA.value,
        Role.PLANEACION.value,
        Role.ADMIN_SISTEMA.value,
    ],
)
def test_el_aviso_de_un_area_no_llega_a_quien_pertenece_a_otra(rol):
    assert can_be_told_the_area_poa_opened(_actor(rol, OTRA_AREA), EL_AREA) is False


@pytest.mark.parametrize("rol", [Role.CAPTURISTA_POA.value, Role.RESPONSABLE_AREA.value])
def test_el_aviso_de_un_area_no_llega_a_quien_no_tiene_area(rol):
    assert can_be_told_the_area_poa_opened(_actor(rol, None), EL_AREA) is False


def test_quien_encabeza_el_area_y_tambien_la_captura_se_entera_una_sola_vez():
    actor = _actor(Role.RESPONSABLE_AREA.value, EL_AREA, Role.CAPTURISTA_POA.value)

    assert can_capture_activity(actor, EL_AREA) is True
    assert can_be_told_the_area_poa_opened(actor, EL_AREA) is True


def test_quien_no_tiene_ningun_rol_no_se_entera_de_la_apertura():
    assert can_be_told_the_area_poa_opened(_actor(None), EL_AREA) is False


# ── Quiénes reciben el aviso del área ────────────────────────────────────────


async def test_el_aviso_llega_a_cada_persona_del_area_y_no_solo_a_la_primera():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )

    quienes = await _destinatarios(usuarios).for_area_notice(EL_AREA)

    assert quienes == {1, 2, 3}


async def test_quien_solo_recibe_por_captura_deja_fuera_al_responsable_del_area():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )
    destinatarios = _destinatarios(usuarios)

    por_captura = await destinatarios.for_assignment(EL_AREA)
    del_aviso = await destinatarios.for_area_notice(EL_AREA)

    assert por_captura == {1}
    assert del_aviso == {1, 2}
    assert por_captura < del_aviso


async def test_una_cuenta_dada_de_baja_no_recibe_el_aviso_del_area():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, False),
    )

    quienes = await _destinatarios(usuarios).for_area_notice(EL_AREA)

    assert quienes == {1}


async def test_las_personas_de_otra_area_no_reciben_el_aviso_del_area():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (OTRA_AREA, {Role.CAPTURISTA_POA.value}, True),
        (OTRA_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )

    quienes = await _destinatarios(usuarios).for_area_notice(EL_AREA)

    assert quienes == {1}


async def test_un_area_sin_nadie_que_la_formule_no_tiene_a_quien_avisarle():
    usuarios = await _los_usuarios((EL_AREA, {Role.CONSULTA.value}, True))

    quienes = await _destinatarios(usuarios).for_area_notice(EL_AREA)

    assert quienes == set()


# ── El aviso que genera la apertura ──────────────────────────────────────────


async def test_la_apertura_avisa_a_cada_persona_con_el_titulo_y_las_dos_fechas():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )
    servicio = ServicioQueAnota()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    entregado = await (await _avisos(usuarios, servicio, EL_AREA)).el_poa_del_area_se_abrio(
        poa_area_id=41, area_id=EL_AREA, desde=desde, hasta=hasta, numero=1
    )

    assert entregado.personas == 2
    assert entregado.area == f"Área número {EL_AREA}"
    assert [uno["user_id"] for uno in servicio.avisados] == [1, 2]
    for uno in servicio.avisados:
        assert uno["notification_type"] == AVISO_DE_LA_APERTURA
        assert uno["title"] == TITULO_DE_LA_APERTURA
        assert uno["entity"] == LA_ENTIDAD_DEL_POA_DEL_AREA
        assert uno["entity_id"] == 41
        assert uno["message"] == (
            "La Dirección de Planeación habilitó el registro de actividades del Programa "
            f"Operativo Anual del área de Área número {EL_AREA}. El periodo permanece abierto "
            "del 3 de noviembre de 2026 al 30 de noviembre de 2026."
        )


def test_el_aviso_de_una_apertura_sin_nombre_de_area_no_deja_el_hueco_a_la_vista():
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    assert el_aviso_de_la_apertura(None, desde, hasta, 1) == (
        "La Dirección de Planeación habilitó el registro de actividades del Programa Operativo "
        "Anual de un área. El periodo permanece abierto del 3 de noviembre de 2026 al "
        "30 de noviembre de 2026."
    )


async def test_el_aviso_de_un_periodo_nuevo_dice_que_es_nuevo_y_trae_las_fechas_nuevas():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    await (await _avisos(usuarios, servicio, EL_AREA)).el_poa_del_area_se_abrio(
        poa_area_id=41,
        area_id=EL_AREA,
        desde=date(2027, 1, 7),
        hasta=date(2027, 2, 1),
        numero=2,
    )

    assert servicio.avisados[0]["message"] == (
        "La Dirección de Planeación habilitó un periodo nuevo para el registro de actividades "
        f"del Programa Operativo Anual del área de Área número {EL_AREA}. El periodo permanece "
        "abierto del 7 de enero de 2027 al 1 de febrero de 2027."
    )


async def test_el_mismo_periodo_del_mismo_poa_lleva_el_mismo_origen_para_cada_persona():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )
    servicio = ServicioQueAnota()
    avisos = await _avisos(usuarios, servicio, EL_AREA)
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE
    argumentos = dict(poa_area_id=41, area_id=EL_AREA, desde=desde, hasta=hasta)

    await avisos.el_poa_del_area_se_abrio(**argumentos, numero=1)
    await avisos.el_poa_del_area_se_abrio(**argumentos, numero=1)
    await avisos.el_poa_del_area_se_abrio(**argumentos, numero=2)

    por_persona = [(uno["user_id"], uno["source_event_id"]) for uno in servicio.avisados]
    assert por_persona[0] == por_persona[2]
    assert por_persona[1] == por_persona[3]
    assert por_persona[0][1] != por_persona[1][1]
    assert por_persona[4][1] != por_persona[0][1]
    assert por_persona[5][1] != por_persona[1][1]


async def test_un_poa_distinto_con_el_mismo_numero_de_periodo_no_comparte_el_origen():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()
    avisos = await _avisos(usuarios, servicio, EL_AREA)
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    await avisos.el_poa_del_area_se_abrio(
        poa_area_id=41, area_id=EL_AREA, desde=desde, hasta=hasta, numero=1
    )
    await avisos.el_poa_del_area_se_abrio(
        poa_area_id=42, area_id=EL_AREA, desde=desde, hasta=hasta, numero=1
    )

    assert servicio.avisados[0]["source_event_id"] != servicio.avisados[1]["source_event_id"]


async def test_un_area_sin_a_quien_avisarle_se_reporta_con_cero_personas():
    usuarios = await _los_usuarios((EL_AREA, {Role.CONSULTA.value}, True))
    servicio = ServicioQueAnota()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    entregado = await (await _avisos(usuarios, servicio, EL_AREA)).el_poa_del_area_se_abrio(
        poa_area_id=41, area_id=EL_AREA, desde=desde, hasta=hasta, numero=1
    )

    assert entregado == AvisoEntregado(area_id=EL_AREA, area=f"Área número {EL_AREA}", personas=0)
    assert servicio.avisados == []


# ── El aviso que la Dirección de Planeación redacta ──────────────────────────


async def test_el_aviso_de_planeacion_llega_a_cada_persona_de_cada_area_elegida():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (EL_AREA, {Role.RESPONSABLE_AREA.value}, True),
        (OTRA_AREA, {Role.CAPTURISTA_POA.value}, True),
    )
    servicio = ServicioQueAnota()

    entregados = await (await _avisos(usuarios, servicio, EL_AREA, OTRA_AREA)).planeacion_redacto(
        [EL_AREA, OTRA_AREA],
        titulo="Entrega del Programa Operativo Anual",
        mensaje="Las áreas entregan su Programa Operativo Anual antes del cierre del periodo.",
    )

    assert [(uno.area_id, uno.personas) for uno in entregados] == [(EL_AREA, 2), (OTRA_AREA, 1)]
    assert [uno["user_id"] for uno in servicio.avisados] == [1, 2, 3]
    for uno in servicio.avisados:
        assert uno["notification_type"] == AVISO_DE_PLANEACION
        assert uno["title"] == "Entrega del Programa Operativo Anual"
        assert uno["entity"] == LA_ENTIDAD_DEL_AREA
    assert [uno["entity_id"] for uno in servicio.avisados] == [EL_AREA, EL_AREA, OTRA_AREA]


async def test_el_aviso_de_planeacion_reporta_el_area_que_no_tiene_a_quien_avisarle():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (OTRA_AREA, {Role.CONSULTA.value}, True),
    )
    servicio = ServicioQueAnota()

    entregados = await (await _avisos(usuarios, servicio, EL_AREA, OTRA_AREA)).planeacion_redacto(
        [EL_AREA, OTRA_AREA], titulo="Un aviso", mensaje="El cuerpo del aviso."
    )

    assert [(uno.area_id, uno.area, uno.personas) for uno in entregados] == [
        (EL_AREA, f"Área número {EL_AREA}", 1),
        (OTRA_AREA, f"Área número {OTRA_AREA}", 0),
    ]


async def test_el_titulo_y_el_mensaje_del_aviso_se_recortan_sin_invisibles():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
        [EL_AREA],
        titulo=f"  Un aviso con holgura {ESPACIO_DE_ANCHO_CERO} ",
        mensaje=f" {ESPACIO_DE_ANCHO_CERO}El cuerpo del aviso.  ",
    )

    assert servicio.avisados[0]["title"] == "Un aviso con holgura"
    assert servicio.avisados[0]["message"] == "El cuerpo del aviso."


@pytest.mark.parametrize("titulo", ["", "   ", ESPACIO_DE_ANCHO_CERO, f" {ESPACIO_DE_ANCHO_CERO} "])
async def test_un_aviso_sin_titulo_que_leer_se_rechaza(titulo):
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    with pytest.raises(ValidationError) as caido:
        await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
            [EL_AREA], titulo=titulo, mensaje="El cuerpo del aviso."
        )

    assert caido.value.message == ESCRIBA_EL_TITULO_DEL_AVISO
    assert servicio.avisados == []


@pytest.mark.parametrize("mensaje", ["", "   ", ESPACIO_DE_ANCHO_CERO])
async def test_un_aviso_sin_mensaje_que_leer_se_rechaza(mensaje):
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    with pytest.raises(ValidationError) as caido:
        await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
            [EL_AREA], titulo="Un aviso", mensaje=mensaje
        )

    assert caido.value.message == ESCRIBA_EL_MENSAJE_DEL_AVISO
    assert servicio.avisados == []


async def test_un_aviso_sin_ninguna_area_elegida_no_se_convierte_en_uno_para_todas():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    with pytest.raises(ValidationError) as caido:
        await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
            [], titulo="Un aviso", mensaje="El cuerpo del aviso."
        )

    assert caido.value.message == ELIJA_AL_MENOS_UN_AREA_PARA_EL_AVISO
    assert servicio.avisados == []


async def test_un_aviso_para_todas_las_areas_se_dirige_a_cada_area_en_servicio():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (OTRA_AREA, {Role.RESPONSABLE_AREA.value}, True),
    )
    servicio = ServicioQueAnota()

    entregados = await (await _avisos(usuarios, servicio, EL_AREA, OTRA_AREA)).planeacion_redacto(
        None, titulo="Un aviso", mensaje="El cuerpo del aviso."
    )

    assert [uno.area_id for uno in entregados] == [EL_AREA, OTRA_AREA]
    assert [uno["user_id"] for uno in servicio.avisados] == [1, 2]


async def test_un_aviso_para_todas_las_areas_deja_fuera_a_las_retiradas_del_servicio():
    usuarios = await _los_usuarios(
        (EL_AREA, {Role.CAPTURISTA_POA.value}, True),
        (OTRA_AREA, {Role.CAPTURISTA_POA.value}, True),
    )
    servicio = ServicioQueAnota()
    areas = await _las_areas(EL_AREA, OTRA_AREA)
    retirada = await areas.get_by_id(OTRA_AREA)
    retirada.is_active = False
    await areas.update(retirada)

    entregados = await AreaNotices(_destinatarios(usuarios), servicio, areas).planeacion_redacto(
        None, titulo="Un aviso", mensaje="El cuerpo del aviso."
    )

    assert [uno.area_id for uno in entregados] == [EL_AREA]
    assert [uno["user_id"] for uno in servicio.avisados] == [1]


async def test_un_aviso_dirigido_a_un_area_retirada_del_servicio_se_rechaza():
    usuarios = await _los_usuarios((OTRA_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()
    areas = await _las_areas(EL_AREA, OTRA_AREA)
    retirada = await areas.get_by_id(OTRA_AREA)
    retirada.is_active = False
    await areas.update(retirada)

    with pytest.raises(ValidationError) as caido:
        await AreaNotices(_destinatarios(usuarios), servicio, areas).planeacion_redacto(
            [OTRA_AREA], titulo="Un aviso", mensaje="El cuerpo del aviso."
        )

    assert retirada.name in caido.value.message
    assert servicio.avisados == []


async def test_un_aviso_dirigido_a_un_area_que_no_existe_se_rechaza():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    with pytest.raises(ValidationError) as caido:
        await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
            [10**8], titulo="Un aviso", mensaje="El cuerpo del aviso."
        )

    assert caido.value.message == EL_AREA_DEL_AVISO_NO_EXISTE
    assert servicio.avisados == []


async def test_un_aviso_para_todas_las_areas_sin_ninguna_area_en_servicio_se_rechaza():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()

    with pytest.raises(ValidationError) as caido:
        await AreaNotices(
            _destinatarios(usuarios), servicio, await _las_areas()
        ).planeacion_redacto(None, titulo="Un aviso", mensaje="El cuerpo del aviso.")

    assert caido.value.message == NO_HAY_NINGUNA_AREA_EN_SERVICIO_QUE_AVISAR
    assert servicio.avisados == []


async def test_dos_redacciones_iguales_son_dos_avisos_distintos():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueAnota()
    avisos = await _avisos(usuarios, servicio, EL_AREA)
    argumentos = dict(titulo="Un aviso", mensaje="El cuerpo del aviso.")

    await avisos.planeacion_redacto([EL_AREA], **argumentos)
    await avisos.planeacion_redacto([EL_AREA], **argumentos)

    assert servicio.avisados[0]["source_event_id"] != servicio.avisados[1]["source_event_id"]


# ── El aviso no puede tumbar la apertura ─────────────────────────────────────


async def test_la_apertura_queda_hecha_aunque_el_aviso_no_se_pueda_entregar():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    avisos = AvisosQueSeCaen()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    reparto = await OpenInstitutionalPoa(
        tablero.repo, tablero.ejercicios, tablero.areas, avisos
    ).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
        )
    )

    assert avisos.intentos == 1
    assert [uno.poa_area.area_id for uno in reparto.opened] == [area]
    assert await tablero.repo.find_poa_area(ejercicio, area) is not None


async def test_un_area_que_no_se_pudo_avisar_no_deja_sin_aviso_a_las_demas():
    tablero = _tablero_en_memoria()
    areas = sorted([await tablero.nueva_area(), await tablero.nueva_area()])
    ejercicio = await tablero.nuevo_ejercicio()

    @dataclass
    class SeCaeConLaPrimera:
        avisadas: list[int] = field(default_factory=list)

        async def el_poa_del_area_se_abrio(self, **valores):
            if not self.avisadas:
                self.avisadas.append(valores["area_id"])
                raise RuntimeError("El riel de notificaciones no contesta")
            self.avisadas.append(valores["area_id"])

    avisos = SeCaeConLaPrimera()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    reparto = await OpenInstitutionalPoa(
        tablero.repo, tablero.ejercicios, tablero.areas, avisos
    ).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio, area_ids=areas, opens_on=desde, closes_on=hasta
        )
    )

    assert avisos.avisadas == areas
    assert [uno.poa_area.area_id for uno in reparto.opened] == areas


async def test_la_apertura_avisa_solo_de_lo_que_de_verdad_se_abrio():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    avisos = AvisosQueAnotan()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE
    abrir = OpenInstitutionalPoa(tablero.repo, tablero.ejercicios, tablero.areas, avisos)
    orden = OpenInstitutionalPoaCommand(
        exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
    )

    primera = await abrir.execute(orden)
    segunda = await abrir.execute(orden)

    assert [uno.poa_area.area_id for uno in primera.opened] == [area]
    assert [uno.poa_area.area_id for uno in segunda.already_open] == [area]
    assert segunda.opened == []
    assert [uno["area_id"] for uno in avisos.aperturas] == [area]


async def test_lo_que_ya_estaba_abierto_no_genera_ningun_aviso():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE
    orden = OpenInstitutionalPoaCommand(
        exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
    )
    await OpenInstitutionalPoa(tablero.repo, tablero.ejercicios, tablero.areas).execute(orden)
    avisos = AvisosQueAnotan()

    reparto = await OpenInstitutionalPoa(
        tablero.repo, tablero.ejercicios, tablero.areas, avisos
    ).execute(orden)

    assert [uno.poa_area.area_id for uno in reparto.already_open] == [area]
    assert avisos.aperturas == []


async def test_la_apertura_le_dice_al_aviso_el_poa_el_area_las_fechas_y_el_numero():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    avisos = AvisosQueAnotan()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE

    reparto = await OpenInstitutionalPoa(
        tablero.repo, tablero.ejercicios, tablero.areas, avisos
    ).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
        )
    )

    assert avisos.aperturas == [
        {
            "poa_area_id": reparto.opened[0].poa_area.id,
            "area_id": area,
            "desde": desde,
            "hasta": hasta,
            "numero": 1,
        }
    ]


async def test_habilitar_un_periodo_nuevo_avisa_con_el_numero_del_periodo_nuevo():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE
    await OpenInstitutionalPoa(tablero.repo, tablero.ejercicios, tablero.areas).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
        )
    )
    avisos = AvisosQueAnotan()

    reabierto = await ReopenPoaArea(tablero.repo, tablero.areas, avisos).execute(
        ReopenPoaAreaCommand(
            exercise_id=ejercicio,
            area_id=area,
            opens_on=date(2027, 1, 7),
            closes_on=date(2027, 2, 1),
            reason="El área no entregó en la fecha dispuesta",
        )
    )

    assert avisos.aperturas == [
        {
            "poa_area_id": reabierto.poa_area.id,
            "area_id": area,
            "desde": date(2027, 1, 7),
            "hasta": date(2027, 2, 1),
            "numero": 2,
        }
    ]


async def test_habilitar_un_periodo_nuevo_queda_hecho_aunque_el_aviso_se_caiga():
    tablero = _tablero_en_memoria()
    area = await tablero.nueva_area()
    ejercicio = await tablero.nuevo_ejercicio()
    desde, hasta = DEL_3_AL_30_DE_NOVIEMBRE
    await OpenInstitutionalPoa(tablero.repo, tablero.ejercicios, tablero.areas).execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio, area_ids=[area], opens_on=desde, closes_on=hasta
        )
    )
    avisos = AvisosQueSeCaen()

    reabierto = await ReopenPoaArea(tablero.repo, tablero.areas, avisos).execute(
        ReopenPoaAreaCommand(
            exercise_id=ejercicio,
            area_id=area,
            opens_on=date(2027, 1, 7),
            closes_on=date(2027, 2, 1),
            reason="El área no entregó en la fecha dispuesta",
        )
    )

    assert avisos.intentos == 1
    assert (await tablero.repo.current_capture_window(reabierto.poa_area.id)).number == 2


async def test_el_riel_caido_si_hace_fallar_el_aviso_que_planeacion_redacta():
    usuarios = await _los_usuarios((EL_AREA, {Role.CAPTURISTA_POA.value}, True))
    servicio = ServicioQueSeCae()

    with pytest.raises(RuntimeError):
        await (await _avisos(usuarios, servicio, EL_AREA)).planeacion_redacto(
            [EL_AREA], titulo="Un aviso", mensaje="El cuerpo del aviso."
        )

    assert servicio.intentos == 1
