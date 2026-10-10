from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class EmailOutbox(Timestamps, Base):
    """Email waiting to be sent, or sent. Rows commit with the change they announce (an approval request, an
    invitation), so a rolled-back change never sends mail. Retried with back-off; `failed` after MAX_ATTEMPTS."""

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_due", "next_attempt_at", postgresql_where=text("status = 'queued'")),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    to_address: Mapped[str] = mapped_column(Text)
    to_name: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    text_body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text)
    related_id: Mapped[str | None] = mapped_column(Text)  # approval id, user id, …
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))  # queued | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
