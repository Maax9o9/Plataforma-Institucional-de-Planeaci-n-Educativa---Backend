"""Composicion de casos de uso de evidencias."""

from fastapi import Request

from ..application.use_cases.manage_evidence import AttachEvidence, ReplaceEvidence


def get_attach_evidence_use_case(request: Request) -> AttachEvidence:
    return AttachEvidence(request.app.state.evidence_repository, request.app.state.event_bus)


def get_replace_evidence_use_case(request: Request) -> ReplaceEvidence:
    return ReplaceEvidence(request.app.state.evidence_repository, request.app.state.event_bus)
