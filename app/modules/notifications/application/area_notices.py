from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.shared.domain.calendar import el_dia_en_letras
from app.shared.domain.captured_text import recortado_sin_invisibles
from app.shared.domain.exceptions import ValidationError

AVISO_DE_LA_APERTURA = "poa_apertura_del_area"
AVISO_DE_PLANEACION = "aviso_de_planeacion"

LARGO_DEL_TITULO = 200
LARGO_DEL_MENSAJE = 2000

TITULO_DE_LA_APERTURA = "Habilitación del periodo de captura"

LA_ENTIDAD_DEL_POA_DEL_AREA = "poa_inst_area"
LA_ENTIDAD_DEL_AREA = "area"

ESCRIBA_EL_TITULO_DEL_AVISO = (
    "Escriba el título del aviso: es lo que las áreas leen en la lista de avisos antes de abrirlo."
)
ESCRIBA_EL_MENSAJE_DEL_AVISO = "Escriba el mensaje del aviso que recibirán las áreas."

ELIJA_AL_MENOS_UN_AREA_PARA_EL_AVISO = (
    "Elija al menos un área a la que dirigir el aviso, o diríjalo a todas las áreas."
)
EL_AREA_DEL_AVISO_NO_EXISTE = (
    "Una de las áreas a las que dirige el aviso no existe. Revise el catálogo de áreas antes de "
    "continuar."
)
NO_HAY_NINGUNA_AREA_EN_SERVICIO_QUE_AVISAR = (
    "No hay ninguna área en servicio a la que dirigir el aviso. Revise el catálogo de áreas antes "
    "de continuar."
)


def el_area_del_aviso_esta_retirada(area_name: str) -> str:
    return (
        f"El área de {area_name} está retirada del servicio y no recibe avisos. Quítela de la "
        "lista o vuelva a darla de alta antes de continuar."
    )


def el_aviso_de_la_apertura(area_name: str | None, desde: date, hasta: date, numero: int) -> str:
    de_quien = "de un área" if area_name is None else f"del área de {area_name}"
    lo_que_hizo = (
        "habilitó el registro de actividades"
        if numero <= 1
        else "habilitó un periodo nuevo para el registro de actividades"
    )
    return (
        f"La Dirección de Planeación {lo_que_hizo} del Programa Operativo Anual {de_quien}. "
        f"El periodo permanece abierto del {el_dia_en_letras(desde)} al "
        f"{el_dia_en_letras(hasta)}."
    )


@dataclass(frozen=True)
class AvisoEntregado:
    area_id: int
    area: str | None
    personas: int


class AreaNotices:
    def __init__(self, recipients, notification_service, areas) -> None:
        self.recipients = recipients
        self.notification_service = notification_service
        self.areas = areas

    async def el_poa_del_area_se_abrio(
        self, *, poa_area_id: int, area_id: int, desde: date, hasta: date, numero: int
    ) -> AvisoEntregado:
        area = await self.areas.get_by_id(area_id)
        return await self._repartir(
            area_id,
            area_name=None if area is None else area.name,
            tipo=AVISO_DE_LA_APERTURA,
            titulo=TITULO_DE_LA_APERTURA,
            mensaje=el_aviso_de_la_apertura(
                None if area is None else area.name, desde, hasta, numero
            ),
            entidad=LA_ENTIDAD_DEL_POA_DEL_AREA,
            entidad_id=poa_area_id,
            clave_del_evento=f"{AVISO_DE_LA_APERTURA}:{poa_area_id}:{numero}",
        )

    async def planeacion_redacto(
        self, area_ids: list[int] | None, *, titulo: str, mensaje: str
    ) -> list[AvisoEntregado]:
        escrito = recortado_sin_invisibles(titulo)
        dicho = recortado_sin_invisibles(mensaje)
        if not escrito:
            raise ValidationError(ESCRIBA_EL_TITULO_DEL_AVISO)
        if not dicho:
            raise ValidationError(ESCRIBA_EL_MENSAJE_DEL_AVISO)
        redaccion = uuid4()
        entregados = []
        for area in await self._las_areas_elegidas(area_ids):
            entregados.append(
                await self._repartir(
                    area.id,
                    area_name=area.name,
                    tipo=AVISO_DE_PLANEACION,
                    titulo=escrito,
                    mensaje=dicho,
                    entidad=LA_ENTIDAD_DEL_AREA,
                    entidad_id=area.id,
                    clave_del_evento=f"{AVISO_DE_PLANEACION}:{redaccion}:{area.id}",
                )
            )
        return entregados

    async def _las_areas_elegidas(self, area_ids: list[int] | None) -> list:
        if area_ids is None:
            en_servicio = sorted(await self.areas.list(active_only=True), key=lambda una: una.id)
            if not en_servicio:
                raise ValidationError(NO_HAY_NINGUNA_AREA_EN_SERVICIO_QUE_AVISAR)
            return en_servicio
        elegidas = sorted(set(area_ids))
        if not elegidas:
            raise ValidationError(ELIJA_AL_MENOS_UN_AREA_PARA_EL_AVISO)
        resueltas = []
        for area_id in elegidas:
            area = await self.areas.get_by_id(area_id)
            if area is None:
                raise ValidationError(EL_AREA_DEL_AVISO_NO_EXISTE)
            if not area.is_active:
                raise ValidationError(el_area_del_aviso_esta_retirada(area.name))
            resueltas.append(area)
        return resueltas

    async def _repartir(
        self,
        area_id: int,
        *,
        area_name: str | None,
        tipo: str,
        titulo: str,
        mensaje: str,
        entidad: str,
        entidad_id: int,
        clave_del_evento: str,
    ) -> AvisoEntregado:
        personas = sorted(await self.recipients.for_area_notice(area_id))
        for persona in personas:
            await self.notification_service.notify_user(
                user_id=persona,
                notification_type=tipo,
                title=titulo,
                message=mensaje,
                entity=entidad,
                entity_id=entidad_id,
                source_event_id=uuid5(NAMESPACE_URL, f"{clave_del_evento}:{persona}"),
            )
        return AvisoEntregado(area_id=area_id, area=area_name, personas=len(personas))
