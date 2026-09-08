"""Composición de casos de uso de la cédula institucional POA."""

from fastapi import Request

from ..application.use_cases.manage_cedula import (
    AddPoaFormActivity,
    AddPoaFormIndicator,
    CapturePoaIndicatorTotal,
    CreatePoaForm,
    IssuePoaForm,
    RecordPoaFollowUp,
    UpdatePoaFollowUpJustification,
    UpdatePoaForm,
    UpdatePoaFormActivity,
    UpdatePoaFormIndicator,
)


def get_create_form_use_case(request: Request) -> CreatePoaForm:
    return CreatePoaForm(
        request.app.state.poa_form_repository,
        request.app.state.poa_repository,
        request.app.state.area_repository,
        request.app.state.event_bus,
        request.app.state.period_repository,
        request.app.state.unit_of_work,
    )


def get_add_form_indicator_use_case(request: Request) -> AddPoaFormIndicator:
    return AddPoaFormIndicator(
        request.app.state.poa_form_repository,
        request.app.state.event_bus,
        request.app.state.area_repository,
    )


def get_update_form_use_case(request: Request) -> UpdatePoaForm:
    return UpdatePoaForm(
        request.app.state.poa_form_repository,
        request.app.state.area_repository,
        request.app.state.event_bus,
    )


def get_update_form_indicator_use_case(request: Request) -> UpdatePoaFormIndicator:
    return UpdatePoaFormIndicator(
        request.app.state.poa_form_repository,
        request.app.state.event_bus,
        request.app.state.area_repository,
    )


def get_capture_indicator_total_use_case(request: Request) -> CapturePoaIndicatorTotal:
    return CapturePoaIndicatorTotal(
        request.app.state.poa_form_repository,
        request.app.state.period_repository,
        request.app.state.poa_repository,
        request.app.state.event_bus,
        request.app.state.area_repository,
    )


def get_add_form_activity_use_case(request: Request) -> AddPoaFormActivity:
    return AddPoaFormActivity(
        request.app.state.poa_form_repository,
        request.app.state.area_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_update_form_activity_use_case(request: Request) -> UpdatePoaFormActivity:
    return UpdatePoaFormActivity(
        request.app.state.poa_form_repository,
        request.app.state.area_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_record_follow_up_use_case(request: Request) -> RecordPoaFollowUp:
    return RecordPoaFollowUp(
        request.app.state.poa_form_repository,
        request.app.state.period_repository,
        request.app.state.poa_repository,
        request.app.state.event_bus,
    )


def get_update_follow_up_justification_use_case(
    request: Request,
) -> UpdatePoaFollowUpJustification:
    return UpdatePoaFollowUpJustification(
        request.app.state.poa_form_repository,
        request.app.state.event_bus,
    )


def get_issue_form_use_case(request: Request) -> IssuePoaForm:
    return IssuePoaForm(
        request.app.state.poa_form_repository,
        request.app.state.period_repository,
        request.app.state.poa_repository,
        request.app.state.event_bus,
        request.app.state.evidence_repository,
        request.app.state.area_repository,
    )
