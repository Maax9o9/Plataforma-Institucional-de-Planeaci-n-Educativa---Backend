from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class EmailTemplateModel(Base):
    __tablename__ = "plantillas_correo"

    tipo: Mapped[str] = mapped_column(String(60), primary_key=True)
    contenido: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    actualizado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
