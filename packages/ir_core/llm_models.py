"""Output models for every prompt in prompts/ (front matter `output_model`). LLM responses are validated against
these; anything else fails the call (CLAUDE.md LLM rules).

Shapes follow what each prompt asks the model to return. Models are strict (extra keys are invalid) so a drifting
response fails validation and is retried once, instead of being half-understood. Modules built in later phases may
tighten their own model; change the prompt and its model together.
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Certainty = Annotated[float, Field(ge=0, le=1)]
AnswerType = Literal["free_text", "choice", "duration", "number", "yes_no", "actor"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, regex_engine="python-re")


class JsonPatchOp(Strict):
    """RFC 6902 op proposed by a model. Same path guard as the patch envelope: no /stories or managed fields."""

    op: Literal["add", "remove", "replace", "move", "copy", "test"]
    path: Annotated[str, Field(pattern=r"^/(?!stories)(?!process/version)(?!process/updated_at).*")]
    from_: str | None = Field(None, alias="from")
    value: Any = None


# ---------------------------------------------------------------- M2 extract_process

class Citation(Strict):
    block_ids: list[str]
    excerpt: Annotated[str, Field(max_length=300)]
    extraction_certainty: Certainty


class ActorCandidate(Citation):
    name: str
    kind: Literal["human_role", "team", "system", "external_party"]
    description: str = ""


class AttributeCandidate(Strict):
    name: str
    type: str = "string"


class EntityCandidate(Citation):
    name: str
    description: str = ""
    attributes: list[AttributeCandidate] = []


class StepCandidate(Citation):
    type: Literal["task", "decision", "wait", "event", "start", "end"]
    name: str
    description: str = ""
    performer: str | None = None
    inputs: list[str] = []
    outputs: list[str] = []
    order_hint: int | None = None
    outcomes: list[str] = []
    control: Literal["automated", "hitl_review", "human_task", "approval", "unknown"] = "unknown"


class RuleCandidate(Citation):
    name: str
    criteria: str
    step: str | None = None
    outcomes: list[str] = []


class ExceptionCandidate(Citation):
    name: str
    trigger: str
    handling: str = "undefined"
    step: str | None = None


class SLACandidate(Citation):
    name: str
    duration: str | None = None  # ISO 8601 when stated
    step: str | None = None
    breach_action: str | None = None


class TermCandidate(Citation):
    term: str
    definition: str | None = None
    ambiguous: bool = False


class ExtractionResult(Strict):
    actors: list[ActorCandidate]
    entities: list[EntityCandidate]
    steps: list[StepCandidate]
    rules: list[RuleCandidate]
    exceptions: list[ExceptionCandidate]
    slas: list[SLACandidate]
    terms: list[TermCandidate]


# ---------------------------------------------------------------- M2 reconcile_match

class MatchDecision(Strict):
    match_id: str | None
    decision: Literal["same", "different", "same_but_conflicts"]
    conflicting_fields: list[str] = []
    reasoning: str


# ---------------------------------------------------------------- M5 gaps_semantic

class SemanticGap(Strict):
    type: Literal["ambiguous_term", "undefined_threshold", "implied_missing_step", "unclear_ownership_of_data",
                  "missing_exception_path", "hitl_undefined", "approval_gate_incomplete"]
    target_ids: Annotated[list[str], Field(min_length=1)]
    title: str
    why_it_matters: str
    question: str
    answer_type: AnswerType
    suggested_answers: list[str] = []
    topic_tags: list[str] = []
    severity: Literal["blocking", "major", "minor"] = "major"


class SemanticGapList(Strict):
    gaps: list[SemanticGap]


# ---------------------------------------------------------------- M6

class PhrasedQuestion(Strict):
    text: str
    answer_type: AnswerType
    suggested_answers: list[str] = []


class AnswerInterpretation(Strict):
    ops: list[JsonPatchOp]
    interpretation_confidence: Certainty
    follow_up_question: str | None
    summary: str


class InterviewTurn(Strict):
    action: Literal["ask", "propose"]
    message: str | None = None
    answer_text: str | None = None


# ---------------------------------------------------------------- M0

class IntakeQuestion(Strict):
    text: str
    why: str
    answer_type: Literal["free_text", "choice", "duration", "number", "yes_no", "actor", "multi_choice"]
    suggested_answers: list[str] = []


class IntakeInterpretation(Strict):
    ops: list[JsonPatchOp]
    captured: list[str]
    assumptions: list[str] = []
    follow_up_question: str | None


class Playback(Strict):
    summary: str


class DraftedAC(Strict):
    ac_id: Annotated[str, Field(pattern=r"^ac_[a-z0-9_]{1,60}$")]
    applies_to: Annotated[list[str], Field(min_length=1)]  # the step, plus the exception or rule it exercises
    title: str
    given: Annotated[list[str], Field(min_length=1)]
    when: Annotated[list[str], Field(min_length=1)]
    then: Annotated[list[str], Field(min_length=1)]
    kind: Literal["happy_path", "edge_case", "negative", "nfr"] = "happy_path"


class StepOutcome(Strict):
    node_id: str
    outcome: str
    goal_ids: list[str] = []


class DraftedACs(Strict):
    criteria: list[DraftedAC]
    outcomes: list[StepOutcome] = []


# ---------------------------------------------------------------- M7 / M12

class PolishedStory(Strict):
    i_want: str
    so_that: str


class StoryRefinement(Strict):
    ops: list[JsonPatchOp]
    summary: list[str]
    clarifying_question: str | None
    answer: str | None


# ---------------------------------------------------------------- M11 improve_suggest

class SuggestionEvidence(Strict):
    source_id: str | None = None
    locator: str
    excerpt: str


class SuggestedChange(Strict):
    title: Annotated[str, Field(max_length=90)]
    kind: Literal["automate_step", "automate_with_review", "add_human_queue", "deterministic_rule", "add_integration",
                  "remove_step", "merge_steps", "add_sla"]
    target_refs: list[str] = []
    change_summary: str
    rationale: str
    evidence: Annotated[list[SuggestionEvidence], Field(min_length=1, max_length=3)]
    minutes_saved_per_case: float | None  # recomputed by the guardrails from the effort data
    qualitative: str | None = None  # the benefit in words, when there is no effort figure
    controls: str
    risk: str
    confidence: Certainty
    ops: list[JsonPatchOp]
    source: Literal["heuristic", "llm"] = "heuristic"


class NotSuggested(Strict):
    target: str
    reason: str


class SuggestionList(Strict):
    suggestions: list[SuggestedChange]
    not_suggested: list[NotSuggested] = []


# Prompt front matter `output_model` → model. The gateway refuses to start if a prompt names anything else.
LLM_OUTPUT_MODELS: dict[str, type[BaseModel]] = {m.__name__: m for m in (
    ExtractionResult, MatchDecision, SemanticGapList, PhrasedQuestion, AnswerInterpretation, InterviewTurn,
    IntakeQuestion, IntakeInterpretation, Playback, DraftedACs, PolishedStory, StoryRefinement, SuggestionList,
    SuggestedChange,
)}
