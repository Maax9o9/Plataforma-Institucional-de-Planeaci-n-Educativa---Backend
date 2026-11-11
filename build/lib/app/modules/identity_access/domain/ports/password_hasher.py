"""Abstraccion para no acoplar los casos de uso al algoritmo de hash."""

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, value: str) -> str: ...

    def verify(self, value: str, hashed_value: str) -> bool: ...
