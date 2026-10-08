"""Transactional outbox: events are written in the same transaction as the state change they announce.

A relay (P1) publishes unpublished rows to Redis Streams and sets published_at, so delivery is at-least-once.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Timestamps
from .events import EventEnvelope


class EventOutbox(Timestamps, Base):
    __tablename__ = "events_outbox"
    __table_args__ = (
        Index("ix_events_outbox_unpublished", "created_at", postgresql_where=text("published_at IS NULL")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # = envelope.event_id
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the full envelope, published as-is
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


async def enqueue_event(session: AsyncSession, event: EventEnvelope) -> EventOutbox:
    """Add the event to the caller's transaction. Nothing is published unless that transaction commits."""
    row = EventOutbox(id=event.event_id, type=event.type, payload=event.model_dump(mode="json"))
    session.add(row)
    await session.flush()
    return row
