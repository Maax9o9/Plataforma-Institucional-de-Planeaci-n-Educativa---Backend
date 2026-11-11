"""Objetos de valor del catalogo maestro de indicadores."""

from enum import StrEnum


class IndicatorPeriodicity(StrEnum):
    MONTHLY = "mensual"
    QUARTERLY = "trimestral"
    FOUR_MONTHLY = "cuatrimestral"
    ANNUAL = "anual"
