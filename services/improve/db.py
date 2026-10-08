from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import services.ideas.db  # noqa: F401  (FK targets)
import services.ir_store.db  # noqa: F401
from services.common.db import Base, Timestamps


class SuggestionRow(Timestamps, Base):
    """One M11 suggestion (schemas/suggestion.schema.json), keyed by idea: S01 is only unique within an idea."""

    __tablename__ = "suggestions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # S01…
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    target_refs: Mapped[list[str]] = mapped_column(ARRAY(Text))
    title: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    benefit: Mapped[dict[str, Any]] = mapped_column(JSONB)
    controls: Mapped[str] = mapped_column(Text)
    risk: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text)  # proposed | accepted | rejected | edited
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    applied_patch_id: Mapped[str | None] = mapped_column(ForeignKey("ir_patches.id"))
    source: Mapped[str] = mapped_column(Text)

    def as_suggestion(self) -> dict:
        s = {"suggestion_id": self.id, "idea_id": self.idea_id, "kind": self.kind,
             "target_refs": list(self.target_refs), "title": self.title, "change_summary": self.change_summary,
             "rationale": self.rationale, "evidence": self.evidence, "benefit": self.benefit,
             "controls": self.controls, "confidence": float(self.confidence), "status": self.status,
             "decision": self.decision, "ops": self.ops}
        if self.risk is not None:
            s["risk"] = self.risk
        return s
