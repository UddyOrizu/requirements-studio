"""Improvement suggestion — mirrors schemas/suggestion.schema.json (M11)."""
from typing import Annotated, Literal

from pydantic import Field

from .common import AnyNumber, Closed, Confidence, DateTime, JsonPointer, LooseOp, SuggestionId, absent


class SuggestionEvidence(Closed):
    source_id: str
    locator: str
    excerpt: str


class Benefit(Closed):
    minutes_saved_per_case: AnyNumber | None = absent()
    cases_per_month: AnyNumber | None = absent()
    hours_saved_per_month: AnyNumber | None = absent()
    qualitative: str = absent()


class SuggestionDecision(Closed):
    by: str = absent()
    at: DateTime = absent()
    reason: str = absent()


class Suggestion(Closed):
    suggestion_id: SuggestionId
    idea_id: str
    kind: Literal["automate_step", "automate_with_review", "add_human_queue", "deterministic_rule", "add_integration",
                  "remove_step", "merge_steps", "add_sla"]
    target_refs: Annotated[list[JsonPointer], Field(min_length=1)]
    title: Annotated[str, Field(max_length=90)]
    change_summary: str
    rationale: str
    evidence: list[SuggestionEvidence]
    benefit: Benefit
    controls: str
    risk: str = absent()
    confidence: Confidence
    status: Literal["proposed", "accepted", "rejected", "edited"]
    decision: SuggestionDecision | None = absent()
    ops: list[LooseOp]
