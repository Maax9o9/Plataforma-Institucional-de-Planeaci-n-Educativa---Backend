"""Implementacion segura que solo registra el correo."""

from __future__ import annotations

import logging

logger = logging.getLogger("email.console")


class ConsoleEmailSender:
    async def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> None:
        logger.info(
            "[correo simulado] para=%s asunto=%s cuerpo=%s",
            recipient,
            subject,
            text_body or html_body[:200],
        )
