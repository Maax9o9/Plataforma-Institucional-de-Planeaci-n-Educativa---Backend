"""Estados validos del ciclo de vida de un periodo."""

from enum import StrEnum


class PeriodStatus(StrEnum):
    DRAFT = "borrador"
    OPEN = "abierto"
    CLOSED = "cerrado"


class PeriodType(StrEnum):
    INDICATORS = "indicadores"
    POA = "poa"


class Periodicity(StrEnum):
    MONTHLY = "mensual"
    QUARTERLY = "trimestral"
    FOUR_MONTHLY = "cuatrimestral"
    ANNUAL = "anual"
