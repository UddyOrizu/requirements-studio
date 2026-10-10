"""M6 tables used by M0's "Not sure — ask someone" (docs/04). Routing, batching and delivery arrive in P9."""
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.identity_audit.db  # noqa: F401  (FK target)
import services.ir_store.db  # noqa: F401  (FK target)
from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class Sme(Timestamps, Base):
    __tablename__ = "smes"
    __table_args__ = (Index("ix_smes_topic_embedding", "topic_embedding", postgresql_using="hnsw",
                            postgresql_ops={"topic_embedding": "vector_cosine_ops"}),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    role_title: Mapped[str | None] = mapped_column(Text)
    actor_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    topic_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    topic_embedding: Mapped[Any | None] = mapped_column(Vector(1536))  # M6 routing (P9)
    process_ids_owned: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    max_open_questions: Mapped[int | None] = mapped_column(Integer)
    working_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    out_of_office_until: Mapped[date | None] = mapped_column(Date)
    delegate_sme_id: Mapped[str | None] = mapped_column(ForeignKey("smes.id"))


class Question(Timestamps, Base):
    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_sme_id_status", "sme_id", "status"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # q_…
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))
    origin: Mapped[str] = mapped_column(Text)  # gap_routing | intake_ask_someone
    asked_by: Mapped[str | None] = mapped_column(Text)
    gap_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    sme_id: Mapped[str | None] = mapped_column(ForeignKey("smes.id"))  # the directory entry, when there is one
    assignee_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))  # the person asked (internal user)
    batch_id: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)  # in_app (portal) | email
    text: Mapped[str] = mapped_column(Text)
    context_snippet: Mapped[str | None] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(Text)
    suggested_answers: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Answer(Timestamps, Base):
    """An answer to a question (docs/04). From "ask someone", the person answers in the app; turning the answer into
    an IR change stays with the requester (or M6's interpretation, P9), so patch_id is often null."""

    __tablename__ = "answers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    answered_by: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    structured_value: Mapped[Any | None] = mapped_column(JSONB)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    interpretation_confidence: Mapped[Any | None] = mapped_column(Numeric)
    follow_up_question: Mapped[str | None] = mapped_column(Text)
