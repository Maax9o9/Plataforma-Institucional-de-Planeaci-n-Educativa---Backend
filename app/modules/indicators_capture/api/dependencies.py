"""Composicion de casos de uso de capturas."""

from fastapi import Request

from ..application.use_cases.manage_capture import EditCapture, RegisterCapture, SendCapture


def get_register_capture_use_case(request: Request) -> RegisterCapture:
    return RegisterCapture(
        repository=request.app.state.capture_repository,
        indicator_reader=request.app.state.indicator_repository,
        period_reader=request.app.state.period_repository,
        event_bus=request.app.state.event_bus,
    )


def get_edit_capture_use_case(request: Request) -> EditCapture:
    return EditCapture(
        repository=request.app.state.capture_repository,
        period_reader=request.app.state.period_repository,
        event_bus=request.app.state.event_bus,
    )


def get_send_capture_use_case(request: Request) -> SendCapture:
    return SendCapture(
        repository=request.app.state.capture_repository,
        period_reader=request.app.state.period_repository,
        evidence_reader=request.app.state.evidence_repository,
        event_bus=request.app.state.event_bus,
    )
