from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, CHAR, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.ir_store.db  # noqa: F401  (FK targets)
from services.common.db import Base, Timestamps


class GapRow(Timestamps, Base):
    __tablename__ = "gaps"
    __table_args__ = (
        Index("uq_gaps_process_id_fingerprint_unresolved", "process_id", "fingerprint", unique=True,
              postgresql_where=text("status NOT IN ('resolved')")),
        Index("ix_gaps_process_id_status_priority", "process_id", "status", text("priority DESC")),
    )

    # Gap ids are unique per process (migration 0007): an as-is and its to-be share element ids.
    process_id: Mapped[str] = mapped_column(ForeignKey("processes.id"), primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(CHAR(40))
    type: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    detector: Mapped[str] = mapped_column(Text)
    target_refs: Mapped[list[str]] = mapped_column(ARRAY(Text))
    title: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    question: Mapped[dict[str, Any]] = mapped_column(JSONB)
    routing: Mapped[dict[str, Any]] = mapped_column(JSONB)
    priority: Mapped[Decimal] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text)
    ir_version_detected: Mapped[int] = mapped_column(Integer)
    resolved_by_patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    waiver: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    def as_gap(self) -> dict:
        """gap.schema.json shape."""
        return {"gap_id": self.id, "process_id": self.process_id, "fingerprint": self.fingerprint, "type": self.type,
                "severity": self.severity, "detector": self.detector, "target_refs": list(self.target_refs),
                "title": self.title, "why_it_matters": self.why_it_matters, "question": self.question,
                "routing": self.routing, "priority": float(self.priority), "status": self.status,
                "ir_version_detected": self.ir_version_detected, "resolved_by_patch_id": self.resolved_by_patch_id}
