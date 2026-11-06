from __future__ import annotations

import pytest

from app.modules.institutional_catalogs.domain.pide_workbook import (
    FilaDeAcciones,
    FilaDeObjetivos,
    WorkbookShapeError,
    clave_del_padre,
    clave_y_denominacion,
    clave_y_denominacion_del_eje,
    plan_de_carga,
)
from app.modules.institutional_catalogs.domain.strategic_tree_entities import NodeKind

EJE_1 = "Eje 1. Garantizar la Formación Integral que Desarrolle las Capacidades del Estudiante."
LINEA_1 = "1.1.1.1. Acompañamiento académico y vinculación con la trayectoria."
ACCION_1 = "1.1.1.1.1. Actualizar el Programa Institucional de Tutorías."
ACCION_2 = "1.1.1.1.2. Garantizar el acompañamiento académico de las tutorías."
INDICADOR_1 = "Programa de Tutoría Actualizado / Programa de Tutoría x 100"


def fila(numero: int, *, eje=EJE_1, linea=LINEA_1, accion=ACCION_1, indicador=INDICADOR_1):
    return FilaDeAcciones(
        numero=numero, eje=eje, linea=linea, accion=accion, indicador=indicador
    )


def test_la_clave_se_separa_de_la_denominacion():
    assert clave_y_denominacion(ACCION_1) == (
        "1.1.1.1.1",
        "Actualizar el Programa Institucional de Tutorías.",
    )


def test_la_clave_del_eje_sale_de_su_numero_y_no_de_la_palabra_eje():
    assert clave_y_denominacion_del_eje(EJE_1) == (
        "1",
        "Garantizar la Formación Integral que Desarrolle las Capacidades del Estudiante.",
    )


def test_una_clave_sin_punto_final_tambien_se_reconoce():
    assert clave_y_denominacion("3.1.1 Asegurar el modelo educativo.") == (
        "3.1.1",
        "Asegurar el modelo educativo.",
    )


def test_el_padre_de_una_clave_es_la_clave_sin_su_ultima_parte():
    assert clave_del_padre("1.1.1.1.1") == "1.1.1.1"
    assert clave_del_padre("1") is None


def test_una_accion_arrastra_consigo_los_cuatro_niveles_que_la_sostienen():
    plan = plan_de_carga([fila(2)])

    assert [(nodo.kind, nodo.key) for nodo in plan.nodos] == [
        (NodeKind.EJE, "1"),
        (NodeKind.OBJETIVO_GENERAL, "1.1"),
        (NodeKind.OBJETIVO_ESPECIFICO, "1.1.1"),
        (NodeKind.LINEA_ESTRATEGICA, "1.1.1.1"),
        (NodeKind.ACCION, "1.1.1.1.1"),
    ]


def test_el_padre_de_cada_nodo_es_la_clave_de_arriba():
    plan = plan_de_carga([fila(2)])

    assert [nodo.parent_key for nodo in plan.nodos] == [None, "1", "1.1", "1.1.1", "1.1.1.1"]


def test_el_indicador_de_la_fila_queda_en_la_accion_y_no_en_sus_ancestros():
    plan = plan_de_carga([fila(2)])

    porque = {nodo.key: nodo.indicator_formula for nodo in plan.nodos}
    assert porque["1.1.1.1.1"] == INDICADOR_1
    assert porque["1.1.1.1"] is None
    assert porque["1"] is None


def test_dos_acciones_de_la_misma_linea_no_duplican_los_ancestros():
    plan = plan_de_carga([fila(2), fila(3, accion=ACCION_2)])

    claves = [nodo.key for nodo in plan.nodos]
    assert claves == ["1", "1.1", "1.1.1", "1.1.1.1", "1.1.1.1.1", "1.1.1.1.2"]


def test_los_hermanos_se_ordenan_por_el_orden_en_que_aparecen():
    plan = plan_de_carga([fila(2), fila(3, accion=ACCION_2)])

    orden = {nodo.key: nodo.order for nodo in plan.nodos}
    assert orden["1.1.1.1.1"] == 1
    assert orden["1.1.1.1.2"] == 2


def test_los_nombres_de_los_objetivos_salen_de_la_otra_hoja():
    objetivos = [
        FilaDeObjetivos(
            numero=2,
            eje=EJE_1,
            objetivo_general="1.1 Objetivo General\n\nConsolidar un proceso formativo innovador.",
            clave_especifico="1.1.1.",
            objetivo_especifico="Fortalecer el Programa Institucional de Tutorías.",
        )
    ]

    plan = plan_de_carga([fila(2)], objetivos)

    nombres = {nodo.key: nodo.name for nodo in plan.nodos}
    assert nombres["1.1"] == "Consolidar un proceso formativo innovador."
    assert nombres["1.1.1"] == "Fortalecer el Programa Institucional de Tutorías."


def test_sin_la_hoja_de_objetivos_el_nombre_es_provisional_y_se_avisa():
    plan = plan_de_carga([fila(2)])

    nombres = {nodo.key: nodo.name for nodo in plan.nodos}
    assert nombres["1.1"] == "Objetivo general 1.1"
    assert any("1.1" in aviso and "provisional" in aviso for aviso in plan.avisos)


def test_una_accion_sin_eje_detiene_la_carga_y_dice_en_que_fila():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga([fila(7, eje=None)])

    assert "fila 7" in str(roto.value)


def test_una_accion_que_no_cuelga_de_la_linea_con_la_que_aparece_detiene_la_carga():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga([fila(9, accion="1.1.1.2.1. Otra cosa que no es de esa línea.")])

    assert "1.1.1.2.1" in str(roto.value)
    assert "1.1.1.1" in str(roto.value)


def test_una_clave_de_accion_con_menos_partes_de_las_debidas_detiene_la_carga():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga([fila(4, accion="1.1.1.1 Esta es una línea, no una acción.")])

    assert "5 partes" in str(roto.value).replace("las 5", "5")


def test_una_clave_de_accion_repetida_dice_donde_estaba_la_primera():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga([fila(2), fila(8)])

    assert "fila 2" in str(roto.value)
    assert "fila 8" in str(roto.value)


def test_una_linea_que_no_pertenece_al_eje_con_el_que_aparece_detiene_la_carga():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga(
            [
                fila(
                    5,
                    linea="2.1.1.1. Línea del eje dos.",
                    accion="2.1.1.1.1. Acción del eje dos.",
                )
            ]
        )

    assert "eje 1" in str(roto.value)


def test_un_libro_sin_filas_de_acciones_detiene_la_carga():
    with pytest.raises(WorkbookShapeError) as roto:
        plan_de_carga([])

    assert "Líneas, acciones e indicadores" in str(roto.value)


def test_una_accion_sin_indicador_se_carga_y_se_avisa():
    plan = plan_de_carga([fila(2, indicador=None)])

    assert any("1.1.1.1.1" in aviso for aviso in plan.avisos)
    assert [nodo for nodo in plan.nodos if nodo.key == "1.1.1.1.1"][0].indicator_formula is None


def test_la_cuenta_por_nivel_dice_cuantos_entran_de_cada_uno():
    plan = plan_de_carga([fila(2), fila(3, accion=ACCION_2)])

    assert plan.cuantos_por_nivel() == {
        "eje": 1,
        "objetivo_general": 1,
        "objetivo_especifico": 1,
        "linea_estrategica": 1,
        "accion": 2,
    }


def test_una_fila_sin_accion_se_salta_sin_romper_la_carga():
    plan = plan_de_carga([fila(2), fila(3, accion=None, indicador=None)])

    assert [nodo.key for nodo in plan.nodos if nodo.kind is NodeKind.ACCION] == ["1.1.1.1.1"]


def _libro(filas_de_acciones, *, nombre="Líneas, acciones e indicadores", objetivos=None) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = nombre
    hoja.append(["Eje", "Línea estratégica", "Acción", "Indicador"])
    for celdas in filas_de_acciones:
        hoja.append(list(celdas))
    if objetivos is not None:
        otra = libro.create_sheet("Ejes y objetivos")
        otra.append(["Eje", "Objetivo general del eje", "Núm.", "Objetivos específicos"])
        for celdas in objetivos:
            otra.append(list(celdas))
    cuerpo = BytesIO()
    libro.save(cuerpo)
    return cuerpo.getvalue()


def test_el_eje_y_la_linea_se_arrastran_a_las_filas_que_los_dejan_en_blanco():
    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    acciones, _ = filas_del_libro(
        _libro(
            [
                [EJE_1, LINEA_1, ACCION_1, INDICADOR_1],
                [None, None, ACCION_2, "Otro indicador"],
            ]
        )
    )

    assert [fila.eje for fila in acciones] == [EJE_1, EJE_1]
    assert [fila.linea for fila in acciones] == [LINEA_1, LINEA_1]


def test_la_accion_y_el_indicador_no_se_arrastran_nunca():
    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    acciones, _ = filas_del_libro(
        _libro(
            [
                [EJE_1, LINEA_1, ACCION_1, INDICADOR_1],
                [None, "2.1.1.1. Otra línea.", None, None],
            ]
        )
    )

    assert [fila.accion for fila in acciones] == [ACCION_1, None]
    assert [fila.indicador for fila in acciones] == [INDICADOR_1, None]


def test_una_fila_en_blanco_entre_dos_con_datos_no_llega_al_plan():
    from io import BytesIO

    from openpyxl import Workbook

    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Líneas, acciones e indicadores"
    hoja.append(["Eje", "Línea estratégica", "Acción", "Indicador"])
    hoja.append([EJE_1, LINEA_1, ACCION_1, INDICADOR_1])
    hoja.cell(row=4, column=3, value=ACCION_2)
    hoja.cell(row=4, column=4, value="Otro indicador")
    cuerpo = BytesIO()
    libro.save(cuerpo)

    acciones, _ = filas_del_libro(cuerpo.getvalue())

    assert [fila.numero for fila in acciones] == [2, 4]
    assert [fila.accion for fila in acciones] == [ACCION_1, ACCION_2]


def test_el_numero_de_fila_que_se_informa_es_el_del_excel():
    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    acciones, _ = filas_del_libro(
        _libro([[EJE_1, LINEA_1, ACCION_1, INDICADOR_1], [None, None, ACCION_2, "Otro"]])
    )

    assert [fila.numero for fila in acciones] == [2, 3]


def test_un_libro_sin_la_hoja_de_objetivos_se_lee_igual():
    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    acciones, objetivos = filas_del_libro(_libro([[EJE_1, LINEA_1, ACCION_1, INDICADOR_1]]))

    assert len(acciones) == 1
    assert objetivos == []


def test_un_libro_sin_la_hoja_acordada_dice_cual_falta():
    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    with pytest.raises(WorkbookShapeError) as roto:
        filas_del_libro(_libro([[EJE_1, LINEA_1, ACCION_1, INDICADOR_1]], nombre="Hoja1"))

    assert "Hoja1" in str(roto.value)


def test_un_archivo_que_no_es_un_libro_no_se_lee():
    from app.shared.domain.exceptions import UnsupportedMediaTypeError

    from app.modules.institutional_catalogs.infrastructure.pide_workbook_reader import (
        filas_del_libro,
    )

    with pytest.raises(UnsupportedMediaTypeError):
        filas_del_libro(b"PK esto no es un xlsx")
