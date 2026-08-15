"""Composicion de scoring."""

from fastapi import Request

from ..application.use_cases.calculate_evaluation import CalculateEvaluation
from ..application.use_cases.update_thresholds import (
    UpdateGlobalThresholds,
    UpdateIndicatorThresholds,
)


def get_calculate_evaluation_use_case(request: Request) -> CalculateEvaluation:
    return CalculateEvaluation(
        indicators=request.app.state.indicator_repository,
        captures=request.app.state.capture_repository,
        goals=request.app.state.indicator_repository,
        config=request.app.state.threshold_config_repository,
        event_bus=request.app.state.event_bus,
    )


def get_update_global_thresholds_use_case(request: Request) -> UpdateGlobalThresholds:
    return UpdateGlobalThresholds(
        request.app.state.threshold_config_repository,
        request.app.state.event_bus,
    )


def get_update_indicator_thresholds_use_case(request: Request) -> UpdateIndicatorThresholds:
    return UpdateIndicatorThresholds(
        request.app.state.indicator_repository,
        request.app.state.event_bus,
    )
