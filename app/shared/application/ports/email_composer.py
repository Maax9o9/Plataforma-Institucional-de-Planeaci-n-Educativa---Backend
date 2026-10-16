"""Composición de correo independiente de SMTP, almacenamiento y HTTP."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ComposedEmail:
    subject: str
    html: str
    text: str


class EmailComposer(Protocol):
    async def render(
        self,
        key: str,
        *,
        recipient_name: str,
        detail: str,
        action_url: str | None = None,
        overrides: dict[str, str] | None = None,
    ) -> ComposedEmail: ...
