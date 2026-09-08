"""PDF legible de seguimientos con texto largo, separado de la consulta."""

from io import BytesIO
from xml.sax.saxutils import escape

from app.modules.indicators_reports.application.service import ReportResult


def export_pdf(report: ReportResult) -> BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, leftMargin=36, rightMargin=36)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"POA — {escape(report.report_type)}", styles["Title"])]
    story.append(
        Paragraph("Fuente: cédulas actuales. Datos de captura, no validación.", styles["Normal"])
    )
    for row in report.rows:
        story.append(Spacer(1, 12))
        story.append(
            Paragraph(
                f"Cédula {row.get('cedula_id')} — Actividad "
                f"{escape(str(row.get('actividad_clave', '')))}",
                styles["Heading2"],
            )
        )
        data = [[Paragraph("Campo", styles["Normal"]), Paragraph("Valor", styles["Normal"])]]
        for key, value in row.items():
            data.append(
                [
                    Paragraph(escape(key.replace("_", " ")), styles["Normal"]),
                    Paragraph(escape(str(value) if value is not None else "—"), styles["Normal"]),
                ]
            )
        table = LongTable(data, colWidths=[155, document.width - 155], repeatRows=1, splitInRow=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    if not report.rows:
        story.append(Paragraph("Sin resultados", styles["Normal"]))
    document.build(story)
    output.seek(0)
    return output
