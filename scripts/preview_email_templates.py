"""Genera vistas locales con datos ficticios, sin BD, tokens válidos ni SMTP.

Uso: python scripts/preview_email_templates.py --output var/email-previews
"""

import argparse
import base64
from pathlib import Path

from app.modules.email_templates.infrastructure.rendering import (
    ASSETS,
    TEMPLATE_ROOT,
    FileTemplateCatalog,
    HtmlEmailRenderer,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="var/email-previews")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    renderer = HtmlEmailRenderer()
    for definition in FileTemplateCatalog().list():
        email = renderer.render(
            definition,
            definition.content,
            recipient_name="María Fernanda López Hernández",
            detail=(
                "Tu enlace personal vence en 24 horas. Sólo puede usarse una vez. "
                "No lo compartas con otras personas."
                if definition.key == "invitacion"
                else "Fecha límite: 2026-12-31. Cédula Objetivo 6 · Septiembre–Diciembre 2026. "
                "Actividad 6.1.1: faltan progreso, alcance y evidencia. "
                "Revisa tus pendientes en la plataforma."
            ),
            action_url="https://example.invalid/plataforma?ejemplo=" + "a" * 90,
        )
        html = email.html
        for cid, filename in ASSETS.items():
            data = base64.b64encode((TEMPLATE_ROOT / "assets" / filename).read_bytes()).decode()
            html = html.replace(f"cid:{cid}", f"data:image/png;base64,{data}")
        path = output / f"{definition.key}.html"
        path.write_text(html, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
