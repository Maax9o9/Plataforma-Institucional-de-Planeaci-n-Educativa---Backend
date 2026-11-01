from __future__ import annotations

from fastapi import Request

from ..application.use_cases.manage_poa_area import OpenPoaArea, SavePoaActivity, SubmitPoaArea


def get_open_poa_area(request: Request) -> OpenPoaArea:
    return OpenPoaArea(
        request.app.state.poa_area_repository,
        request.app.state.poa_repository,
        request.app.state.area_repository,
    )


def get_save_poa_activity(request: Request) -> SavePoaActivity:
    return SavePoaActivity(
        request.app.state.poa_area_repository, request.app.state.strategic_tree_repository
    )


def get_submit_poa_area(request: Request) -> SubmitPoaArea:
    return SubmitPoaArea(request.app.state.poa_area_repository, request.app.state.area_leadership)
