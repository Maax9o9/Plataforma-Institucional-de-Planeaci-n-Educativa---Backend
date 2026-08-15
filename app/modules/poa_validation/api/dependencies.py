from fastapi import Request

from ..application.use_cases.validate_advance import RejectPoaAdvance, ValidatePoaAdvance


def get_validate_poa_advance_use_case(request: Request) -> ValidatePoaAdvance:
    return ValidatePoaAdvance(
        request.app.state.poa_advance_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )


def get_reject_poa_advance_use_case(request: Request) -> RejectPoaAdvance:
    return RejectPoaAdvance(
        request.app.state.poa_advance_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )
