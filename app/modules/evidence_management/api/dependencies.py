"""Composicion de casos de uso de evidencias."""

from fastapi import Request

from ..application.access_control import EvidenceAccessControl
from ..application.use_cases.manage_evidence import AttachEvidence, ReplaceEvidence
from ..application.use_cases.review_evidence import ReviewEvidence


def get_evidence_access_control(request: Request) -> EvidenceAccessControl:
    return EvidenceAccessControl(
        request.app.state.evidence_repository,
        request.app.state.capture_repository,
        request.app.state.period_repository,
        request.app.state.poa_form_repository,
    )


def get_attach_evidence_use_case(request: Request) -> AttachEvidence:
    return AttachEvidence(
        request.app.state.evidence_repository,
        request.app.state.event_bus,
        get_evidence_access_control(request),
        request.app.state.unit_of_work,
    )


def get_review_evidence_use_case(request: Request) -> ReviewEvidence:
    return ReviewEvidence(request.app.state.evidence_repository, request.app.state.event_bus)


def get_replace_evidence_use_case(request: Request) -> ReplaceEvidence:
    return ReplaceEvidence(
        request.app.state.evidence_repository,
        request.app.state.event_bus,
        get_evidence_access_control(request),
        request.app.state.unit_of_work,
    )
