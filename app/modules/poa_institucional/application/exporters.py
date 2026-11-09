from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from app.modules.poa_institucional.domain.impresion import (
    MESES_DEL_EJERCICIO,
    BloqueDeLaAccion,
    PoaParaImprimir,
)

EL_LOGOTIPO = Path(__file__).resolve().parents[3] / "assets" / "marca" / "upchiapas.png"

PROPORCION_DEL_LOGOTIPO = 1818 / 434

TIPO_DE_DOCUMENTO = "Tipo de documento: Registro"

TITULO = "PROGRAMA OPERATIVO ANUAL"

EMISION_DEL_FORMATO = "Enero 2026"

REVISION_DEL_FORMATO = "Revisión: 2"

AL_PIE = (
    "Documento no controlado por medios electrónicos. "
    "Para uso exclusivo de la Universidad Politécnica de Chiapas."
)

INICIALES_DE_LOS_MESES = ("e", "f", "m", "a", "m", "j", "j", "a", "s", "o", "n", "d")

SIN_MONTO = "$0.00"

MESES_EN_LETRA = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

ANCHO_DEL_EJE = 20
ANCHO_DE_LA_ESTRATEGIA = 40
ANCHO_DEL_MES = 13
ANCHO_DE_LA_UNIDAD = 56
ANCHO_DE_LO_PROGRAMADO = 26
ANCHO_DEL_MONTO = 44
MARGEN = 28
ALTO_DEL_ENCABEZADO = 54
CUERPO = 5.8


def export_poa_del_area_pdf(impreso: PoaParaImprimir) -> BytesIO:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=letter,
        leftMargin=MARGEN,
        rightMargin=MARGEN,
        topMargin=MARGEN + ALTO_DEL_ENCABEZADO + 10,
        bottomMargin=MARGEN + 14,
        title=f"Programa Operativo Anual {impreso.anio} — {impreso.area}",
        author="Universidad Politécnica de Chiapas",
    )
    dibujar = _el_encabezado_y_el_pie(documento)
    documento.build(
        _el_cuerpo(documento, impreso), onFirstPage=dibujar, onLaterPages=dibujar
    )
    salida.seek(0)
    return salida


def _estilos():
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()["Normal"]
    return {
        "celda": ParagraphStyle("celda", parent=base, fontSize=CUERPO, leading=7.2),
        "accion": ParagraphStyle(
            "accion", parent=base, fontSize=CUERPO, leading=7.2, fontName="Helvetica-Bold"
        ),
        "unidad": ParagraphStyle(
            "unidad", parent=base, fontSize=CUERPO, leading=7.2, alignment=TA_CENTER
        ),
        "actividad": ParagraphStyle(
            "actividad", parent=base, fontSize=CUERPO, leading=7.2, leftIndent=7
        ),
        "nota": ParagraphStyle(
            "nota",
            parent=base,
            fontSize=6.5,
            leading=9,
            alignment=TA_CENTER,
            textColor="#c92a2a",
        ),
        "firma": ParagraphStyle(
            "firma", parent=base, fontSize=7.5, leading=11, alignment=TA_CENTER
        ),
    }


def _el_cuerpo(documento, impreso: PoaParaImprimir):
    from reportlab.platypus import Paragraph, Spacer

    estilos = _estilos()
    historia = [
        _la_ficha_del_area(documento, impreso, estilos),
        Spacer(1, 8),
        Paragraph(escape(impreso.nota), estilos["nota"]),
        Spacer(1, 8),
        _la_tabla(documento, impreso, estilos),
        Spacer(1, 22),
        _las_firmas(documento, impreso, estilos),
    ]
    return historia


def _la_ficha_del_area(documento, impreso: PoaParaImprimir, estilos):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    etiqueta = documento.width * 0.18
    valor = documento.width * 0.32
    datos = [
        ["Área:", impreso.area, "Responsable:", impreso.responsable],
        ["Fecha de elaboración", _en_letra(impreso), "Año:", str(impreso.anio)],
    ]
    tabla = Table(datos, colWidths=[etiqueta, valor, etiqueta, valor], rowHeights=[22, 22])
    tabla.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#495057")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d9d9d9")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#d9d9d9")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ]
        )
    )
    return tabla


def _en_letra(impreso: PoaParaImprimir) -> str:
    dia = impreso.elaborado_el
    return f"{dia.day} de {MESES_EN_LETRA[dia.month - 1]} de {dia.year}"


def _la_tabla(documento, impreso: PoaParaImprimir, estilos):
    from reportlab.lib import colors
    from reportlab.platypus import LongTable, Paragraph, TableStyle

    fijas = (
        ANCHO_DEL_EJE
        + ANCHO_DE_LA_ESTRATEGIA
        + ANCHO_DEL_MES * 12
        + ANCHO_DE_LA_UNIDAD
        + ANCHO_DE_LO_PROGRAMADO
        + ANCHO_DEL_MONTO
    )
    anchos = [
        ANCHO_DEL_EJE,
        ANCHO_DE_LA_ESTRATEGIA,
        documento.width - fijas,
        *([ANCHO_DEL_MES] * 12),
        ANCHO_DE_LA_UNIDAD,
        ANCHO_DE_LO_PROGRAMADO,
        ANCHO_DEL_MONTO,
    ]

    datos = [
        [
            "Programa Institucional de Desarrollo",
            "",
            "",
            "Calendario",
            *([""] * 11),
            "Metas",
            "",
            "Monto",
        ],
        [
            "Eje",
            "Estrategia",
            "Líneas de acción/Actividades",
            *INICIALES_DE_LOS_MESES,
            "Unidad de medida",
            "Prog.",
            "solicitado",
        ],
    ]
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#495057")),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#d9d9d9")),
        ("SPAN", (0, 0), (2, 0)),
        ("SPAN", (3, 0), (14, 0)),
        ("SPAN", (15, 0), (16, 0)),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (3, 2), (16, -1), "CENTER"),
        ("ALIGN", (0, 2), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), CUERPO),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    renglon = len(datos)
    for bloque in impreso.bloques:
        datos.append(_el_renglon_de_la_accion(bloque, estilos))
        estilo.append(("SPAN", (3, renglon), (16, renglon)))
        renglon += 1
        for actividad in bloque.actividades:
            datos.append(_el_renglon_de_la_actividad(actividad, estilos))
            for mes in MESES_DEL_EJERCICIO:
                if mes in actividad.meses:
                    columna = 2 + mes
                    estilo.append(
                        (
                            "BACKGROUND",
                            (columna, renglon),
                            (columna, renglon),
                            colors.HexColor("#d9d9d9"),
                        )
                    )
            renglon += 1

    if not impreso.bloques:
        datos.append([Paragraph("Sin actividades registradas.", estilos["celda"])] + [""] * 16)
        estilo.append(("SPAN", (0, renglon), (16, renglon)))
        renglon += 1

    datos.append([*([""] * 15), "Total:", SIN_MONTO])
    estilo.append(("SPAN", (0, renglon), (14, renglon)))
    estilo.append(("ALIGN", (15, renglon), (16, renglon), "CENTER"))
    estilo.append(("FONTNAME", (15, renglon), (16, renglon), "Helvetica-Bold"))

    tabla = LongTable(datos, colWidths=anchos, repeatRows=2)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _el_renglon_de_la_accion(bloque: BloqueDeLaAccion, estilos) -> list:
    from reportlab.platypus import Paragraph

    return [
        bloque.eje,
        bloque.estrategia,
        Paragraph(escape(bloque.titulo), estilos["accion"]),
        *([""] * 14),
    ]


def _el_renglon_de_la_actividad(actividad, estilos) -> list:
    from reportlab.platypus import Paragraph

    return [
        "",
        "",
        Paragraph(f"{actividad.numero} · {escape(actividad.denominacion)}", estilos["actividad"]),
        *[actividad.meses.get(mes, "") for mes in MESES_DEL_EJERCICIO],
        Paragraph(escape(actividad.unidad), estilos["unidad"]),
        actividad.programado,
        SIN_MONTO,
    ]


def _las_firmas(documento, impreso: PoaParaImprimir, estilos):
    from reportlab.platypus import Paragraph, Table, TableStyle

    mitad = documento.width / 2
    datos = [
        [Paragraph("Elaboró", estilos["firma"]), Paragraph("Autorizó", estilos["firma"])],
        [
            Paragraph(escape(impreso.responsable.upper()), estilos["firma"]),
            Paragraph("", estilos["firma"]),
        ],
        [
            Paragraph(escape(impreso.area.upper()), estilos["firma"]),
            Paragraph("", estilos["firma"]),
        ],
    ]
    tabla = Table(datos, colWidths=[mitad, mitad], rowHeights=[16, 44, 14])
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, 0), "TOP"),
                ("VALIGN", (0, 1), (-1, -1), "BOTTOM"),
            ]
        )
    )
    return tabla


def _el_encabezado_y_el_pie(documento):
    from reportlab.lib import colors
    from reportlab.platypus import Image, Table, TableStyle

    def dibujar(lienzo, _documento):
        lienzo.saveState()
        ancho = documento.width
        logotipo = ancho * 0.17
        derecha = ancho * 0.17
        centro = ancho - logotipo - derecha
        datos = [
            [_el_logotipo(logotipo), TIPO_DE_DOCUMENTO, EMISION_DEL_FORMATO],
            ["", TITULO, REVISION_DEL_FORMATO],
            ["", "", f"Página: {lienzo.getPageNumber()}"],
        ]
        tabla = Table(
            datos,
            colWidths=[logotipo, centro, derecha],
            rowHeights=[ALTO_DEL_ENCABEZADO / 3] * 3,
        )
        tabla.setStyle(
            TableStyle(
                [
                    ("GRID", (1, 0), (-1, -1), 0.5, colors.HexColor("#495057")),
                    ("BOX", (0, 0), (0, -1), 0.5, colors.HexColor("#495057")),
                    ("SPAN", (0, 0), (0, -1)),
                    ("SPAN", (1, 1), (1, 2)),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (1, 0), (1, 0), 7),
                    ("FONTSIZE", (1, 1), (1, 1), 10),
                    ("FONTSIZE", (2, 0), (2, -1), 5.5),
                ]
            )
        )
        alto = tabla.wrap(ancho, ALTO_DEL_ENCABEZADO)[1]
        tabla.drawOn(lienzo, MARGEN, documento.pagesize[1] - MARGEN - alto)

        lienzo.setFont("Helvetica", 7)
        lienzo.setLineWidth(0.5)
        lienzo.line(MARGEN, MARGEN + 16, documento.pagesize[0] - MARGEN, MARGEN + 16)
        lienzo.drawCentredString(documento.pagesize[0] / 2, MARGEN + 6, AL_PIE)
        lienzo.restoreState()

    def _el_logotipo(ancho):
        if not EL_LOGOTIPO.exists():
            return ""
        cabe = min(ancho - 10, (ALTO_DEL_ENCABEZADO - 12) * PROPORCION_DEL_LOGOTIPO)
        return Image(str(EL_LOGOTIPO), width=cabe, height=cabe / PROPORCION_DEL_LOGOTIPO)

    return dibujar
