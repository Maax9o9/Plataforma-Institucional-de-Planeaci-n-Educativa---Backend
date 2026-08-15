"""DTOs de paginacion reutilizables."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageRequest:
    offset: int = 0
    limit: int = 50

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("offset no puede ser negativo")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit debe estar entre 1 y 100")


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    offset: int
    limit: int
    total: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
