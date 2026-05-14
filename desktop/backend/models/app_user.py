from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(40), default="bd", index=True)
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    approval_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    must_change_password: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_password_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
