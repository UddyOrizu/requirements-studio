"""M12 ideas table (docs/04). The ideas service arrives in P6; M3 uses this to link an idea's as-is and to-be."""
from typing import Any

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base, Timestamps


class Idea(Timestamps, Base):
    __tablename__ = "ideas"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    has_as_is: Mapped[bool]
    as_is_process_id: Mapped[str | None] = mapped_column(ForeignKey("processes.id"))
    to_be_process_id: Mapped[str | None] = mapped_column(ForeignKey("processes.id"))
    session_id: Mapped[str] = mapped_column(Text)  # no FK: idea and session point at each other
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
