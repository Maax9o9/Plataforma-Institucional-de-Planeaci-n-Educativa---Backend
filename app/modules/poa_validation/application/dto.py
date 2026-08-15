from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatePoaAdvanceCommand:
    advance_id: int
    user_id: int


@dataclass(frozen=True)
class RejectPoaAdvanceCommand:
    advance_id: int
    user_id: int
    comment: str
