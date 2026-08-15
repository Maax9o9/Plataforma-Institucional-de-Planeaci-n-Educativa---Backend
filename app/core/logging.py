"""Configuracion minima de logging; se puede sustituir por structlog sin tocar casos de uso."""

from __future__ import annotations

import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
