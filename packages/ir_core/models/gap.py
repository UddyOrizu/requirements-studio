"""Gap — mirrors schemas/gap.schema.json (M5)."""
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from .common import Closed, JsonPointer, NonNegativeNumber, absent

AnswerType = Literal["free_text", "choice", "duration", "number", "yes_no", "actor"]
GapType = Literal[
    "node_without_actor", "decision_missing_branch", "decision_missing_default", "wait_without_timeout",
    "unreachable_node", "no_path_to_end", "undefined_entity_reference", "sla_without_breach_action",
    "exception_without_handling", "node_without_acceptance_criteria", "natural_language_rule_gating_edge",
    "low_confidence_element", "conflicting_sources", "ambiguous_term", "undefined_threshold", "implied_missing_step",
    "unclear_ownership_of_data", "missing_exception_path", "coverage_missing", "story_value_missing",
    "story_priority_missing", "story_edge_cases_missing", "unclear_business_rule", "integration_capability_unknown",
    "hitl_undefined", "approval_gate_incomplete",
]
CoverageSlot = Literal["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C12", "C13",
                       "C14", "C15", "C16", "C17"]


class GapQuestion(Closed):
    text: str
    answer_type: AnswerType
    suggested_answers: list[str] = absent()


class GapRouting(Closed):
    topic_tags: list[str] = absent()
    candidate_actor_ids: list[str] = absent()


class Gap(Closed):
    gap_id: Annotated[str, Field(pattern=r"^gap_[a-z0-9_]{1,60}$")]
    process_id: str
    fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    type: GapType
    severity: Literal["blocking", "major", "minor"]
    detector: Literal["structural", "conflict", "semantic", "confidence", "coverage", "story", "intake"]
    target_refs: Annotated[list[JsonPointer], Field(min_length=1)]
    title: str
    why_it_matters: str
    evidence: list[dict[str, Any]] = absent()
    question: GapQuestion
    routing: GapRouting
    priority: NonNegativeNumber
    status: Literal["open", "asked", "answered", "resolved", "dismissed", "waived"]
    ir_version_detected: int
    resolved_by_patch_id: str | None = absent()
    coverage_slot: CoverageSlot = absent()

    @model_validator(mode="after")
    def _coverage_slot_required(self) -> Self:
        if self.type == "coverage_missing" and "coverage_slot" not in self.model_fields_set:
            raise ValueError("gap type 'coverage_missing' requires coverage_slot")
        return self
