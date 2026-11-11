"""Archivos de diseño de confianza; el texto editable siempre se escapa."""

import json
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from app.shared.application.ports.email_composer import ComposedEmail
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ..domain.entities import TemplateDefinition, personalize, validate_content

TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"
ASSETS = {
    "upchiapas-horizontal": "logo-horizontal.png",
    "upchiapas-dragon": "dragon.png",
}


class FileTemplateCatalog:
    def __init__(self):
        self.definitions = {}
        for path in sorted((TEMPLATE_ROOT / "messages").glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            self.definitions[path.stem] = TemplateDefinition(
                path.stem, item["etiqueta"], validate_content(item["contenido"])
            )

    def list(self):
        return list(self.definitions.values())

    def get(self, key):
        if key not in self.definitions:
            raise ResourceNotFoundError("No existe ese tipo de plantilla de correo.")
        return self.definitions[key]


def paragraphs(text, *, color="#FFFFFF"):
    return "".join(
        f'<p class="copy" style="margin:0 0 16px;font-size:16px;line-height:1.65;color:{color};'
        'overflow-wrap:anywhere;word-break:break-word;">'
        + escape(part).replace("\n", "<br>")
        + "</p>"
        for part in text.split("\n\n")
        if part.strip()
    )


class HtmlEmailRenderer:
    def __init__(self):
        self.base = Template((TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8"))

    def render(self, definition, content, *, recipient_name, detail, action_url):
        values = {key: personalize(value, recipient_name) for key, value in content.items()}
        name = personalize("{{nombre}}", recipient_name)
        button = ""
        if action_url:
            parsed = urlsplit(action_url)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or any(ord(char) < 32 for char in action_url)
            ):
                raise ValidationError(
                    "La URL de acceso debe ser HTTP o HTTPS y no llevar credenciales."
                )
            url = escape(action_url, quote=True)
            button = (
                '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
                '<tr><td class="cta-cell" bgcolor="#00CEBA" '
                'style="background-color:#00CEBA;border-radius:8px;text-align:center;">'
                f'<a class="cta-link" href="{url}" '
                'style="display:inline-block;padding:16px 22px;'
                'overflow-wrap:anywhere;word-break:break-word;'
                "font-size:16px;line-height:1.4;font-weight:bold;color:#10165F;"
                'text-decoration:none;">' + escape(values["texto_boton"]) + "</a></td></tr></table>"
                '<div class="gmail-screen"><div class="gmail-difference">'
                '<p class="fallback" style="font-size:12px;line-height:1.6;'
                'color:#FFFFFF;word-break:break-all;'
                'overflow-wrap:anywhere;">Si el botón no funciona, copia este enlace:<br>'
                f'<a href="{url}" style="color:#FFFFFF;word-break:break-all;">{url}</a></p>'
                '</div></div>'
            )
        html = self.base.substitute(
            subject=escape(values["asunto"]),
            title=escape(values["titulo"]),
            label=escape(definition.label),
            name=escape(name),
            body=paragraphs(values["cuerpo"]),
            detail=paragraphs(detail),
            button=button,
        )
        text = (
            f"Hola {name},\n\n{values['titulo']}\n\n{values['cuerpo']}\n\n{detail}"
            + (f"\n\n{values['texto_boton']}: {action_url}" if action_url else "")
            + "\n\nUniversidad Politécnica de Chiapas\n"
            "Plataforma Institucional de Planeación Educativa"
        )
        return ComposedEmail(values["asunto"], html, text)
