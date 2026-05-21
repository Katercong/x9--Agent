from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class OutreachEmail(Base):
    """A single outreach email record (draft, sent, or failed).

    The MVP flow is:
        draft → (human review in UI) → sent  (or failed)

    ``status`` values:
        ``draft``   - generated but not sent
        ``queued``  - send requested, waiting on Gmail
        ``sent``    - Gmail accepted the message
        ``failed``  - Gmail rejected; ``error_message`` is populated
        ``cancelled`` - user discarded the draft
    """

    __tablename__ = "outreach_emails"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    to_email: Mapped[str] = mapped_column(String(320), index=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(10), default="plain")  # plain | html

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    review_required: Mapped[int] = mapped_column(Integer, default=1)
    auto_send: Mapped[int] = mapped_column(Integer, default=0)

    gmail_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # snapshot of the rendering context — useful for debugging "why did the
    # template look like this for this creator". Stored as JSON string.
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI generation tracking — JSON list of {subject, body} alternates the
    # user could pick from (N-choose-1), the source row for a rollback, and
    # the tone/language that generated this row.
    ai_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_email_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ai_tone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
