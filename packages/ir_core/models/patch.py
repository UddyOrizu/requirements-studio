"""IR patch envelope — mirrors schemas/patch.schema.json (docs/02 §7)."""
from typing import Annotated, Any, Literal

from pydantic import Field

from .common import Closed, Confidence, Open, ProcId, absent

PatchStatus = Literal["proposed", "accepted", "rejected", "applied", "conflicted", "superseded"]


class PatchOp(Open):
    """RFC 6902 operation. The path pattern keeps derived/managed fields out of reach (docs/02 §7 rule 1)."""

    op: Literal["add", "remove", "replace", "move", "copy", "test"]
    path: Annotated[str, Field(pattern=r"^/(?!stories)(?!process/version)(?!process/updated_at).*")]
    from_: str = Field(default=None, alias="from")
    value: Any = absent()


class PatchAuthor(Closed):
    kind: Literal["user", "agent"]
    id: str


class PatchEvidence(Closed):
    question_id: str = absent()
    answer_id: str = absent()
    gap_ids: list[str] = absent()
    source_ids: list[str] = absent()


class Patch(Closed):
    patch_id: str
    process_id: ProcId
    base_version: Annotated[int, Field(ge=0)]
    ops: Annotated[list[PatchOp], Field(min_length=1)]
    author: PatchAuthor
    reason: str
    evidence: PatchEvidence = absent()
    interpretation_confidence: Confidence = absent()
    auto_apply: bool
    status: PatchStatus
    reviewed_by: str | None = absent()
