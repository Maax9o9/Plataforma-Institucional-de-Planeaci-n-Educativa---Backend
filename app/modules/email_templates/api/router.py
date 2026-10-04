"""Edición administrativa de textos y vista previa sin enviar correos."""

import base64
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import require_roles

from ..infrastructure.rendering import ASSETS, TEMPLATE_ROOT

router = APIRouter(
    prefix="/correos/plantillas",
    tags=["Plantillas de correo"],
    dependencies=[Depends(require_roles("admin_sistema", "planeacion_admin"))],
)


class TextChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    asunto: str | None = Field(default=None, min_length=1, max_length=180)
    titulo: str | None = Field(default=None, min_length=1, max_length=160)
    cuerpo: str | None = Field(default=None, min_length=1, max_length=6000)
    texto_boton: str | None = Field(default=None, min_length=1, max_length=60)


class UpdateTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    contenido: TextChanges


class ResetTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre_destinatario: str = Field(default="María López", min_length=1, max_length=150)
    contenido: TextChanges | None = None


class TemplateResponse(BaseModel):
    tipo: str
    etiqueta: str
    contenido: dict[str, str]
    predeterminado: dict[str, str]
    personalizada: bool
    version: int
    actualizado_por: int | None
    actualizado_en: datetime | None
    variables: list[str]


class PreviewResponse(BaseModel):
    asunto: str
    html: str
    texto: str
    es_vista_previa: bool = True


@router.get("", response_model=list[TemplateResponse], summary="Listar plantillas de correo")
async def list_templates(request: Request):
    return await request.app.state.email_template_service.list()


@router.get("/{tipo}", response_model=TemplateResponse, summary="Consultar una plantilla")
async def get_template(tipo: str, request: Request):
    return await request.app.state.email_template_service.get(tipo)


@router.patch("/{tipo}", response_model=TemplateResponse, summary="Personalizar textos futuros")
async def update_template(tipo: str, body: UpdateTemplateRequest, request: Request):
    return await request.app.state.email_template_service.update(
        tipo,
        body.contenido.model_dump(exclude_unset=True),
        body.version,
        request.state.current_user.id,
    )


@router.post(
    "/{tipo}/restaurar", response_model=TemplateResponse, summary="Restaurar texto original"
)
async def reset_template(tipo: str, body: ResetTemplateRequest, request: Request):
    return await request.app.state.email_template_service.update(
        tipo,
        {},
        body.version,
        request.state.current_user.id,
        reset=True,
    )


@router.post(
    "/{tipo}/vista-previa", response_model=PreviewResponse, summary="Previsualizar sin enviar"
)
async def preview_template(tipo: str, body: PreviewRequest, request: Request):
    await request.app.state.email_template_service.get(tipo)
    # Datos ficticios: nunca generar ni exponer tokens válidos en la vista previa.
    detail = (
        "Tu enlace personal vence en 24 horas. Esta es una vista previa sin token válido."
        if tipo == "invitacion"
        else "Ejemplo de aviso: cédula 12, actividad 6.1.1. Revisa las fechas y pendientes "
        "dentro de la plataforma. Estos datos son ficticios."
    )
    email = await request.app.state.email_template_service.render(
        tipo,
        recipient_name=body.nombre_destinatario,
        detail=detail,
        action_url="https://example.invalid/vista-previa",
        overrides=body.contenido.model_dump(exclude_unset=True) if body.contenido else None,
    )
    html = email.html
    for cid, filename in ASSETS.items():
        data = base64.b64encode((TEMPLATE_ROOT / "assets" / filename).read_bytes()).decode("ascii")
        html = html.replace(f"cid:{cid}", f"data:image/png;base64,{data}")
    return PreviewResponse(asunto=email.subject, html=html, texto=email.text)
