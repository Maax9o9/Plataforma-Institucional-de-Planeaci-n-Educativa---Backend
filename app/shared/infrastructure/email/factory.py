"""Factory del proveedor de correo."""

from app.core.config import Settings
from app.shared.application.ports.email_sender import EmailSender

from .console_email_sender import ConsoleEmailSender
from .smtp_email_sender import SmtpEmailSender


def create_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "console":
        return ConsoleEmailSender()
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError(
            "EMAIL_PROVIDER=smtp requiere SMTP_HOST, SMTP_USER y SMTP_PASSWORD."
        )
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        sender=settings.email_sender,
        start_tls=settings.smtp_start_tls,
    )
