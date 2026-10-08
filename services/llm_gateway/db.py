from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

import services.ir_store.db  # noqa: F401  (registers processes, the process_id foreign key target)
from services.common.db import Base, Timestamps
from services.common.uuid7 import uuid7


class LlmCall(Timestamps, Base):
    """One row per provider attempt (or replayed attempt), so cost and failures are traceable to a prompt file."""

    __tablename__ = "llm_calls"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    correlation_id: Mapped[str] = mapped_column(Text)
    process_id: Mapped[str | None] = mapped_column(ForeignKey("processes.id"))
    prompt_file: Mapped[str] = mapped_column(Text)
    prompt_sha256: Mapped[str] = mapped_column(CHAR(64))
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)  # ok | invalid_output | provider_error
    error: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)  # live | record | replay
