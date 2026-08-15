"""Composicion de casos de uso de seguimiento POA."""

from fastapi import Request

from ..application.use_cases.manage_advance import EditAdvance, RegisterAdvance, SendAdvance


def get_register_advance_use_case(request: Request) -> RegisterAdvance:
    return RegisterAdvance(
        request.app.state.poa_advance_repository,
        request.app.state.poa_repository,
        request.app.state.period_repository,
        request.app.state.user_repository,
        request.app.state.criteria_repository,
        request.app.state.event_bus,
    )


def get_edit_advance_use_case(request: Request) -> EditAdvance:
    return EditAdvance(
        request.app.state.poa_advance_repository,
        request.app.state.period_repository,
        request.app.state.event_bus,
    )


def get_send_advance_use_case(request: Request) -> SendAdvance:
    return SendAdvance(
        request.app.state.poa_advance_repository,
        request.app.state.poa_repository,
        request.app.state.period_repository,
        request.app.state.evidence_repository,
        request.app.state.event_bus,
    )
