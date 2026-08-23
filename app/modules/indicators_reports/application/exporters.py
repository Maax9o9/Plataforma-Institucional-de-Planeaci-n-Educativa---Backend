"""Exportadores de reportes sin mezclar formato con la consulta."""

from __future__ import annotations

from io import BytesIO

from .service import ReportResult


def _columns(report: ReportResult) -> list[str]:
    columns: list[str] = []
    for row in report.rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    return columns


def export_xlsx(report: ReportResult) -> BytesIO:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.report_type[:31]
    columns = _columns(report)
    if not columns:
        sheet.append(["Sin resultados"])
    else:
        sheet.append(columns)
        for row in report.rows:
            sheet.append([row.get(column) for column in columns])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def export_pdf(report: ReportResult) -> BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    columns = _columns(report)
    rows = [columns] if columns else [["Sin resultados"]]
    if columns:
        rows.extend([[str(row.get(column, "")) for column in columns] for row in report.rows])
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )
    table = Table(rows)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    document.build([table])
    output.seek(0)
    return output
