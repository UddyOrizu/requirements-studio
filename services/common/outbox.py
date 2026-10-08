"""Transactional outbox: events are written in the same transaction as the state change they announce.

`relay_outbox` (run by the worker) publishes unpublished rows to a Redis Stream and sets published_at. Delivery is
at-least-once: a crash between XADD and commit republishes, so consumers dedupe on event_id.
"""
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import DateTime, Index, Text, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Timestamps, utcnow
from .events import EventEnvelope

EVENT_STREAM = "rs:events"


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


async def relay_outbox(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, *,
                       stream: str = EVENT_STREAM, batch: int = 100) -> int:
    """Publish up to `batch` unpublished events in commit order; returns how many were published.

    SKIP LOCKED lets several workers relay at once without publishing the same row twice.
    """
    async with sessionmaker() as session:
        q = (select(EventOutbox).where(EventOutbox.published_at.is_(None)).order_by(EventOutbox.created_at)
             .limit(batch).with_for_update(skip_locked=True))
        rows = list((await session.execute(q)).scalars())
        for row in rows:
            await redis.xadd(stream, {"event_id": str(row.id), "type": row.type, "event": json.dumps(row.payload)})
            row.published_at = utcnow()
        await session.commit()
        return len(rows)
