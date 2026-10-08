"""M0 tables (docs/04 + migration 0004)."""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, CHAR, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.ideas.db  # noqa: F401  (FK targets)
import services.interviewer.db  # noqa: F401
import services.ir_store.db  # noqa: F401
from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class IntakeSession(Timestamps, Base):
    __tablename__ = "intake_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # is_…
    mode: Mapped[str] = mapped_column(Text)  # idea | as_is
    idea_id: Mapped[str | None] = mapped_column(ForeignKey("ideas.id"))
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))  # the process being worked on now
    requester_user_id: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)  # discover | improve | deepen | validate | done
    status: Mapped[str] = mapped_column(Text)  # active | paused | completed
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    parked: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    current_target: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class IntakeTurn(Timestamps, Base):
    """One timeline entry. `n` is its position (the schema's `seq`)."""

    __tablename__ = "intake_turns"
    __table_args__ = (UniqueConstraint("session_id", "n"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    session_id: Mapped[str] = mapped_column(ForeignKey("intake_sessions.id"))
    n: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    turn: Mapped[str | None] = mapped_column(Text)  # T0, T1, … for requester turns
    process_variant: Mapped[str | None] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(Text)
    target: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    question: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    answer_text: Mapped[str | None] = mapped_column(Text)
    special: Mapped[str | None] = mapped_column(Text)
    ask_sme_id: Mapped[str | None] = mapped_column(ForeignKey("smes.id"))
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    captured: Mapped[list[str] | None] = mapped_column(JSONB)
    assumptions: Mapped[list[str] | None] = mapped_column(JSONB)
    follow_up_question: Mapped[str | None] = mapped_column(Text)
    coverage_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    undone_by_patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))


class Signoff(Timestamps, Base):
    """M8 sign-off of a story at an IR version; it stays valid while the story's closure hash is unchanged."""

    __tablename__ = "signoffs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))
    story_id: Mapped[str] = mapped_column(Text)
    ir_version: Mapped[int] = mapped_column(Integer)
    closure_hash: Mapped[str] = mapped_column(CHAR(64))
    signed_by: Mapped[str] = mapped_column(Text)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoryRefinementRow(Timestamps, Base):
    """M12 refine chat: the instruction, the previewed ops and story before/after, and the patch once applied."""

    __tablename__ = "story_refinements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"))
    story_id: Mapped[str] = mapped_column(Text)
    instruction: Mapped[str] = mapped_column(Text)
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    status: Mapped[str] = mapped_column(Text)  # previewed | applied | discarded
    by: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
