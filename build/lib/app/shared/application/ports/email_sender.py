"""Contrato de envio de correo para cualquier modulo."""

from __future__ import annotations

from typing import Protocol


class EmailSendError(Exception):
    """Error estable de envio, independiente de la libreria SMTP."""


class EmailSender(Protocol):
    async def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> None:
        ...
