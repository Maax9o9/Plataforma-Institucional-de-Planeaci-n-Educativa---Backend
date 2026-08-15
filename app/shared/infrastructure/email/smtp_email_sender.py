"""Implementacion SMTP real, activada solo por configuracion."""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.shared.application.ports.email_sender import EmailSendError


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        start_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.start_tls = start_tls

    async def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body or "Este mensaje requiere un cliente compatible con HTML.")
        message.add_alternative(html_body, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=self.start_tls,
                timeout=15,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"No se pudo enviar correo a {recipient}.") from exc
