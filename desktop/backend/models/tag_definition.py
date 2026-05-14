from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class TagDefinition(Base):
    __tablename__ = "tag_definitions"

    tag_code: Mapped[str] = mapped_column(String(120), primary_key=True)
    tag_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tag_type: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
