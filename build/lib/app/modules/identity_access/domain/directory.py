"""Asignaciones institucionales autorizadas para invitaciones de usuarios."""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import Role


@dataclass(frozen=True, kw_only=True)
class DirectoryAssignment:
    email: str
    area_code: str
    exact_area_name: str
    roles: frozenset[Role]


class InstitutionalDirectory:
    def __init__(self, assignments: tuple[DirectoryAssignment, ...]) -> None:
        self._assignments = assignments
        self._by_email = {item.email.casefold(): item for item in assignments}

    def find_by_email(self, email: str) -> DirectoryAssignment | None:
        return self._by_email.get(email.strip().casefold())

    def list(self) -> tuple[DirectoryAssignment, ...]:
        return self._assignments
