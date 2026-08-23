"""Tipos numericos compartidos por el contrato HTTP."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field

InstitutionalDecimal = Annotated[
    Decimal,
    Field(max_digits=18, decimal_places=4, examples=["5200"]),
]
NonNegativeInstitutionalDecimal = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=4, examples=["40"]),
]
PercentageDecimal = Annotated[
    Decimal,
    Field(max_digits=6, decimal_places=2, examples=["82.50"]),
]
