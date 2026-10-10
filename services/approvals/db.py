from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.ideas.db  # noqa: F401  (FK targets)
import services.identity_audit.db  # noqa: F401
import services.ir_store.db  # noqa: F401
from services.common.db import Base, Timestamps


class ApprovalRequest(Timestamps, Base):
    """One request to one person. kind → subject_id:
    patch_review → ir_patches.id · story_signoff → intake_sessions.id · suggestion → suggestions.id (with idea_id)
    · question → questions.id.

    status: pending → approved | rejected | answered (the assignee decided) | cancelled (the requester withdrew it)
    | closed (decided some other way, e.g. the owner accepted the patch themselves).
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_assignee_status", "assignee_user_id", "status"),
        Index("ix_approval_requests_requested_by_status", "requested_by", "status"),
        Index("ix_approval_requests_subject", "kind", "subject_id"),
        Index("uq_approval_requests_pending", "kind", "subject_id", "assignee_user_id", unique=True,
              postgresql_where=text("status = 'pending'")),
        CheckConstraint("kind IN ('patch_review', 'story_signoff', 'suggestion', 'question')", name="kind"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'answered', 'cancelled', 'closed')",
                        name="status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # apr_…
    kind: Mapped[str] = mapped_column(Text)
    idea_id: Mapped[str | None] = mapped_column(ForeignKey("ideas.id"))
    process_id: Mapped[str | None] = mapped_column(ForeignKey("processes.id"))
    subject_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)  # the requester's note
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    requested_by: Mapped[str] = mapped_column(Text)
    assignee_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    response: Mapped[str | None] = mapped_column(Text)  # the assignee's note or answer
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
