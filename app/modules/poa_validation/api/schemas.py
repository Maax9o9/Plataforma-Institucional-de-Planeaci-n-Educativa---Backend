from pydantic import BaseModel, Field


class RechazarAvanceRequest(BaseModel):
    comentario: str = Field(min_length=1, max_length=1000)
