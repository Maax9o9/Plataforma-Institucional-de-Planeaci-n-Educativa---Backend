"""Autorizacion por objeto para evidencias de indicadores y POA."""

from __future__ import annotations

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ..domain.value_objects import FlowEntity


class EvidenceAccessControl:
    def __init__(self, evidences, captures, advances, periods, poa) -> None:
        self.evidences = evidences
        self.captures = captures
        self.advances = advances
        self.periods = periods
        self.poa = poa

    async def ensure_target_editable(
        self,
        entity: FlowEntity,
        entity_id: int,
        actor: ActorContext,
    ) -> None:
        if entity is FlowEntity.CAPTURE:
            item = await self.captures.get_by_id(entity_id)
            if item is None:
                raise ResourceNotFoundError("La captura no existe.")
            if not actor.is_planning and item.capturer_id != actor.id:
                raise ForbiddenError("El usuario no es el capturista de la captura.")
            period = await self.periods.get_by_id(item.period_id)
            item.ensure_editable(
                period_is_open=period is not None and period.status.value == "abierto"
            )
            if period is None or period.status.value != "abierto":
                from app.shared.domain.exceptions import InvalidStateError

                raise InvalidStateError("El periodo de la captura no esta abierto.")
            return

        item = await self.advances.get_by_id(entity_id)
        if item is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        if not actor.is_planning and item.capturer_id != actor.id:
            raise ForbiddenError("El usuario no es el capturista del avance POA.")
        period = await self.periods.get_by_id(item.period_id)
        item.ensure_editable(
            period_is_open=period is not None and period.status.value == "abierto"
        )

    async def ensure_can_view(self, evidence_id: int, actor: ActorContext) -> None:
        evidence = await self.evidences.get(evidence_id)
        if evidence is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        if actor.is_planning or evidence.uploaded_by == actor.id:
            return
        for link in await self.evidences.list_links(evidence_id):
            if link.entity is FlowEntity.CAPTURE:
                item = await self.captures.get_by_id(link.entity_id)
            else:
                item = await self.advances.get_by_id(link.entity_id)
            if item is not None and item.capturer_id == actor.id:
                return
        raise ForbiddenError("La evidencia no pertenece al usuario.")

    async def ensure_can_replace(self, evidence_id: int, actor: ActorContext) -> None:
        await self.ensure_can_view(evidence_id, actor)
        links = await self.evidences.list_links(evidence_id)
        for link in links:
            await self.ensure_target_editable(link.entity, link.entity_id, actor)

    async def ensure_same_poa_exercise(
        self, evidence_id: int, target_advance_id: int
    ) -> None:
        target_exercise = await self._exercise_for_advance(target_advance_id)
        for link in await self.evidences.list_links(evidence_id):
            if link.entity is not FlowEntity.POA_ADVANCE:
                continue
            if await self._exercise_for_advance(link.entity_id) == target_exercise:
                return
        raise ForbiddenError("La evidencia no pertenece al mismo ejercicio POA.")

    async def list_reusable_for_exercise(
        self, exercise_id: int, actor: ActorContext
    ) -> list:
        if await self.poa.get_exercise(exercise_id) is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        result = []
        for evidence in await self.evidences.list_all():
            if not actor.is_planning and evidence.uploaded_by != actor.id:
                continue
            for link in await self.evidences.list_links(evidence.id):
                if link.entity is not FlowEntity.POA_ADVANCE:
                    continue
                if await self._exercise_for_advance(link.entity_id) == exercise_id:
                    result.append(evidence)
                    break
        return result

    async def _exercise_for_advance(self, advance_id: int) -> int:
        advance = await self.advances.get_by_id(advance_id)
        if advance is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        activity = await self.poa.get_activity(advance.activity_id)
        objective = await self.poa.get_objective(activity.objective_id) if activity else None
        process = await self.poa.get_process(objective.process_id) if objective else None
        if process is None:
            raise ResourceNotFoundError("La estructura del avance POA no existe.")
        return process.exercise_id
