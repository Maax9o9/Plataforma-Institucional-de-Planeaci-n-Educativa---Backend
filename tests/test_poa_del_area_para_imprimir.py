from datetime import date
from decimal import Decimal

import pytest

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    NodeKind,
    StrategicNode,
)
from app.modules.poa_institucional.domain.entities import Activity, MonthlyTarget
from app.modules.poa_institucional.domain.impresion import (
    NOTA_DE_LO_PRESENTADO,
    NOTA_DEL_BORRADOR,
    SIN_ACCION,
    SIN_RESPONSABLE,
    SIN_UNIDAD,
    armar_el_poa_para_imprimir,
)

UNIDADES = {2: ("Informe", "Informes"), 3: ("Minuta", "Minutas")}


def nodo(identificador: int, padre: int | None, nivel: NodeKind, clave: str, nombre: str):
    return StrategicNode(
        id=identificador,
        version_id=1,
        parent_id=padre,
        kind=nivel,
        key=clave,
        name=nombre,
        order=identificador,
    )


EL_ARBOL = [
    nodo(1, None, NodeKind.EJE, "1", "Formación integral"),
    nodo(2, 1, NodeKind.OBJETIVO_GENERAL, "1.1", "Proceso formativo"),
    nodo(3, 2, NodeKind.OBJETIVO_ESPECIFICO, "1.1.1", "Trayectorias"),
    nodo(4, 3, NodeKind.LINEA_ESTRATEGICA, "1.1.1.1", "Acompañamiento académico"),
    nodo(5, 4, NodeKind.ACCION, "1.1.1.1.1", "Actualizar el Programa de Tutorías"),
    nodo(6, 4, NodeKind.ACCION, "1.1.1.1.2", "Capacitar a los tutores"),
    nodo(7, None, NodeKind.EJE, "2", "Docencia"),
    nodo(8, 7, NodeKind.LINEA_ESTRATEGICA, "2.1.1.1", "Profesionalización"),
    nodo(9, 8, NodeKind.ACCION, "2.1.1.1.1", "Certificar a los docentes"),
    nodo(10, 4, NodeKind.ACCION, "1.1.1.1.10", "Evaluar el programa de tutorías"),
    nodo(11, 4, NodeKind.ACCION, "1.1.1.1.3.bis", "Reponer la sesión de tutoría"),
]


def actividad(
    identificador: int,
    *,
    nodo_id: int | None = 5,
    nombre: str = "Equipar el laboratorio",
    unidad: int | None = 2,
    meses: dict[int, str] | None = None,
    activa: bool = True,
    monto: str | None = None,
):
    puestos = meses if meses is not None else {1: "1", 7: "2"}
    return Activity(
        id=identificador,
        poa_area_id=90,
        node_id=nodo_id,
        name=nombre,
        unit_id=unidad,
        evaluation_method="Constancias",
        annual_target=Decimal(3),
        requested_amount=None if monto is None else Decimal(monto),
        monthly=[
            MonthlyTarget(
                month=mes,
                target=Decimal(puestos.get(mes, "0")),
                included=mes in puestos,
            )
            for mes in range(1, 13)
        ],
        is_active=activa,
    )


def armar(actividades, **extra):
    return armar_el_poa_para_imprimir(
        area="Dirección de Planeación Educativa",
        responsable=extra.pop("responsable", "Pascual Ramos García"),
        anio=2027,
        elaborado_el=date(2026, 11, 9),
        presentado=extra.pop("presentado", False),
        actividades=actividades,
        nodos=extra.pop("nodos", EL_ARBOL),
        unidades=extra.pop("unidades", UNIDADES),
    )


class TestLoQueSaleEnElEncabezado:
    def test_lleva_el_area_el_anio_y_la_fecha(self):
        impreso = armar([actividad(1)])

        assert impreso.area == "Dirección de Planeación Educativa"
        assert impreso.anio == 2027
        assert impreso.elaborado_el == date(2026, 11, 9)
        assert impreso.responsable == "Pascual Ramos García"

    def test_un_area_sin_responsable_lo_dice_en_lugar_de_dejarlo_en_blanco(self):
        assert armar([actividad(1)], responsable=None).responsable == SIN_RESPONSABLE

    def test_el_borrador_avisa_que_todavia_puede_cambiar(self):
        assert armar([actividad(1)]).nota == NOTA_DEL_BORRADOR

    def test_lo_presentado_avisa_que_ya_no_admite_cambios(self):
        assert armar([actividad(1)], presentado=True).nota == NOTA_DE_LO_PRESENTADO


class TestComoSeAgrupan:
    def test_cada_accion_es_un_bloque_con_su_eje_y_su_linea_estrategica(self):
        impreso = armar([actividad(1), actividad(2, nodo_id=6)])

        assert [bloque.eje for bloque in impreso.bloques] == ["1", "1"]
        assert [bloque.estrategia for bloque in impreso.bloques] == ["1.1.1.1", "1.1.1.1"]
        assert impreso.bloques[0].titulo == "1.1.1.1.1 · Actualizar el Programa de Tutorías"
        assert impreso.bloques[1].titulo == "1.1.1.1.2 · Capacitar a los tutores"

    def test_varias_actividades_de_una_accion_caen_en_el_mismo_bloque_numeradas(self):
        impreso = armar([actividad(1, nombre="Una"), actividad(2, nombre="Otra")])

        assert len(impreso.bloques) == 1
        assert [una.numero for una in impreso.bloques[0].actividades] == ["1", "2"]
        assert [una.denominacion for una in impreso.bloques[0].actividades] == ["Una", "Otra"]

    def test_los_bloques_van_por_la_clave_de_la_accion_leida_como_numero(self):
        del_eje_dos = actividad(1, nodo_id=9)
        del_eje_uno = actividad(2, nodo_id=5)

        impreso = armar([del_eje_dos, del_eje_uno])

        assert [bloque.eje for bloque in impreso.bloques] == ["1", "2"]

    def test_la_clave_se_lee_como_numero_y_no_como_texto(self):
        impreso = armar([actividad(1, nodo_id=10), actividad(2, nodo_id=6)])

        assert [bloque.titulo.split(" ·")[0] for bloque in impreso.bloques] == [
            "1.1.1.1.2",
            "1.1.1.1.10",
        ]

    def test_una_clave_que_no_es_toda_numeros_no_tumba_el_documento(self):
        impreso = armar([actividad(1, nodo_id=11), actividad(2, nodo_id=10)])

        assert [bloque.titulo.split(" ·")[0] for bloque in impreso.bloques] == [
            "1.1.1.1.3.bis",
            "1.1.1.1.10",
        ]

    def test_una_actividad_alineada_a_la_linea_la_toma_como_su_estrategia(self):
        impreso = armar([actividad(1, nodo_id=4)])

        assert impreso.bloques[0].estrategia == "1.1.1.1"
        assert impreso.bloques[0].eje == "1"

    def test_lo_que_no_tiene_accion_va_al_final_y_no_se_pierde(self):
        impreso = armar([actividad(1, nodo_id=None), actividad(2)])

        assert impreso.bloques[-1].titulo == SIN_ACCION
        assert impreso.bloques[-1].eje == ""
        assert impreso.cuantas_actividades == 2

    def test_una_accion_que_ya_no_esta_en_el_arbol_no_tumba_el_documento(self):
        impreso = armar([actividad(1, nodo_id=404)])

        assert impreso.bloques[-1].titulo == SIN_ACCION

    def test_las_retiradas_no_se_imprimen(self):
        impreso = armar([actividad(1), actividad(2, nombre="Retirada", activa=False)])

        assert impreso.cuantas_actividades == 1


class TestElCalendarioYLasMetas:
    def test_solo_los_meses_incluidos_traen_cantidad(self):
        impreso = armar([actividad(1, meses={1: "1", 7: "2"})])
        renglon = impreso.bloques[0].actividades[0]

        assert renglon.meses == {1: "1", 7: "2"}

    def test_lo_programado_es_la_suma_de_los_meses_incluidos(self):
        impreso = armar([actividad(1, meses={1: "1", 7: "2"})])

        assert impreso.bloques[0].actividades[0].programado == "3"

    def test_la_unidad_va_en_singular_cuando_se_programa_una_sola(self):
        impreso = armar([actividad(1, meses={3: "1"}, unidad=3)])

        assert impreso.bloques[0].actividades[0].unidad == "Minuta"

    def test_la_unidad_va_en_plural_cuando_se_programa_mas_de_una(self):
        impreso = armar([actividad(1, meses={3: "1", 4: "1"}, unidad=3)])

        assert impreso.bloques[0].actividades[0].unidad == "Minutas"

    @pytest.mark.parametrize("unidad", [None, 404])
    def test_sin_unidad_de_medida_lo_dice(self, unidad):
        impreso = armar([actividad(1, unidad=unidad)])

        assert impreso.bloques[0].actividades[0].unidad == SIN_UNIDAD

    def test_una_actividad_sin_meses_programados_sale_en_cero_y_sin_calendario(self):
        impreso = armar([actividad(1, meses={})])
        renglon = impreso.bloques[0].actividades[0]

        assert renglon.meses == {}
        assert renglon.programado == "0"

    def test_las_cantidades_salen_sin_los_ceros_de_la_base(self):
        impreso = armar([actividad(1, meses={2: "1.5000"})])

        assert impreso.bloques[0].actividades[0].meses[2] == "1.5"


class TestElMontoSolicitado:
    def test_cada_actividad_lleva_el_monto_que_pidio(self):
        impreso = armar([actividad(1, monto="1250.5")])

        assert impreso.bloques[0].actividades[0].monto == "$1,250.50"

    def test_una_actividad_sin_monto_capturado_sale_en_cero(self):
        impreso = armar([actividad(1)])

        assert impreso.bloques[0].actividades[0].monto == "$0.00"

    def test_el_total_suma_lo_de_todas_las_actividades(self):
        impreso = armar([
            actividad(1, monto="1250.5"),
            actividad(2, monto="749.5"),
            actividad(3),
        ])

        assert impreso.total == "$2,000.00"

    def test_lo_retirado_no_suma_en_el_total(self):
        impreso = armar([actividad(1, monto="1000"), actividad(2, monto="500", activa=False)])

        assert impreso.total == "$1,000.00"

    def test_un_poa_sin_actividades_tiene_total_en_cero(self):
        impreso = armar([])

        assert impreso.total == "$0.00"
