"""Event envelope (docs/03 §3) and the event types from docs/01 §8."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .db import utcnow
from .uuid7 import uuid7

EventType = Literal[
    "intake.turn_completed", "intake.phase_changed", "source.uploaded", "source.parsed", "extraction.completed",
    "ir.patched", "patch.proposed", "gaps.updated", "question.sent", "question.answered", "question.escalated",
    "dor.evaluated", "export.created",
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid7)
    type: EventType
    process_id: str | None
    ir_version: int | None = None
    occurred_at: datetime = Field(default_factory=utcnow)
    correlation_id: str
    payload: dict[str, Any]
