from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class OutreachTemplate(Base):
    """Email outreach template (subject + body) with placeholder variables.

    Placeholders are rendered with safe ``string.Template``-style ``${var}``
    substitution against the context built from a ``Creator`` row.
    """

    __tablename__ = "outreach_templates"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="zh", index=True)
    # collab type this template is best suited for, e.g. sample_collab,
    # affiliate_collab, brand_awareness_collab. Empty/null means "default".
    collab_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    # product type filter; null means "any product".
    product_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)

    subject_template: Mapped[str] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text)
    is_default: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)

    # AI generation hints — null means "use defaults".
    # tone: formal | casual | friendly. max_length: target body chars.
    tone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sender_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sender_signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
