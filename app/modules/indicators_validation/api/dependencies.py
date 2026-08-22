"""Composicion de validacion."""

from fastapi import Request

from ..application.use_cases.validate_capture import RejectCapture, ValidateCapture


def get_validate_capture_use_case(request: Request) -> ValidateCapture:
    return ValidateCapture(
        request.app.state.capture_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_reject_capture_use_case(request: Request) -> RejectCapture:
    return RejectCapture(
        request.app.state.capture_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )
