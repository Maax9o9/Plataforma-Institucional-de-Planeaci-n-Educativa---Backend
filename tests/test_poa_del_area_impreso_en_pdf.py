from datetime import date

import pytest
from reportlab import rl_config

from app.modules.poa_institucional.application.exporters import export_poa_del_area_pdf
from app.modules.poa_institucional.domain.impresion import (
    BloqueDeLaAccion,
    PoaParaImprimir,
    RenglonDeActividad,
)


@pytest.fixture(autouse=True)
def sin_comprimir():
    """El texto del PDF sólo se puede buscar con los flujos sin comprimir."""
    antes = rl_config.pageCompression
    rl_config.pageCompression = 0
    yield
    rl_config.pageCompression = antes


def renglon(**cambios) -> RenglonDeActividad:
    return RenglonDeActividad(
        **{
            "numero": "1",
            "denominacion": "Equipar el laboratorio de biomecánica",
            "meses": {1: "2"},
            "unidad": "Informes",
            "programado": "2",
            "monto": "$0.00",
            **cambios,
        }
    )


def impreso(actividades, total: str = "$0.00") -> PoaParaImprimir:
    return PoaParaImprimir(
        area="Dirección de Planeación Educativa",
        responsable="Pascual Ramos García",
        anio=2027,
        elaborado_el=date(2026, 11, 10),
        nota="Documento en formulación.",
        bloques=[
            BloqueDeLaAccion(
                eje="1",
                estrategia="1.1",
                titulo="1.1.1 · Actualizar el Programa de Tutorías",
                actividades=actividades,
            )
        ],
        total=total,
    )


def _el_pdf(documento: PoaParaImprimir) -> bytes:
    return export_poa_del_area_pdf(documento).getvalue()


def test_el_monto_de_cada_actividad_sale_impreso():
    datos = _el_pdf(impreso([renglon(monto="$18,500.75")], total="$99,999.99"))

    assert b"18,500.75" in datos


def test_el_total_sale_impreso_al_pie_de_la_tabla():
    datos = _el_pdf(
        impreso([renglon(monto="$1,000.00"), renglon(numero="2", monto="$500.00")], "$1,500.00")
    )

    assert b"Total:" in datos
    assert b"1,500.00" in datos


def test_un_poa_sin_montos_capturados_imprime_ceros_y_no_se_cae():
    datos = _el_pdf(impreso([renglon()]))

    assert datos.startswith(b"%PDF")
    assert b"$0.00" in datos
