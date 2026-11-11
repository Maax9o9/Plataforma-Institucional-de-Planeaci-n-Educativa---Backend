"""DTOs del flujo de validacion."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidateCaptureCommand:
    capture_id: int
    user_id: int


@dataclass(frozen=True)
class RejectCaptureCommand:
    capture_id: int
    user_id: int
    comment: str
