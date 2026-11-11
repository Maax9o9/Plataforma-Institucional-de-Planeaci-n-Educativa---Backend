from __future__ import annotations

from fastapi import Request

from ..application.use_cases.manage_poa_area import (
    OpenInstitutionalPoa,
    ReopenPoaArea,
    SavePoaActivity,
    SubmitPoaArea,
)


def get_open_institutional_poa(request: Request) -> OpenInstitutionalPoa:
    return OpenInstitutionalPoa(
        request.app.state.poa_area_repository,
        request.app.state.poa_repository,
        request.app.state.area_repository,
        request.app.state.area_notices,
    )


def get_reopen_poa_area(request: Request) -> ReopenPoaArea:
    return ReopenPoaArea(
        request.app.state.poa_area_repository,
        request.app.state.area_repository,
        request.app.state.area_notices,
    )


def get_save_poa_activity(request: Request) -> SavePoaActivity:
    return SavePoaActivity(
        request.app.state.poa_area_repository,
        request.app.state.strategic_tree_repository,
        request.app.state.area_repository,
    )


def get_submit_poa_area(request: Request) -> SubmitPoaArea:
    return SubmitPoaArea(
        request.app.state.poa_area_repository,
        request.app.state.area_leadership,
        request.app.state.area_repository,
    )
