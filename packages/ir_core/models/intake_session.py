"""Intake session (M0 conversation timeline) — mirrors schemas/intake-session.schema.json."""
from typing import Annotated, Any, Literal

from pydantic import Field

from .common import Closed, Confidence, DateTime, LooseOp, ProcId, SrcId, absent

Phase = Literal["discover", "improve", "deepen", "validate", "done"]


class TurnTarget(Closed):
    kind: Literal["idea", "slot", "follow_up", "gap", "playback_confirm", "signoff", "suggestion", "story"]
    id: str


class TurnQuestion(Closed):
    text: str
    why: str
    answer_type: Literal["free_text", "choice", "duration", "number", "yes_no", "actor", "multi_choice"] = absent()
    suggested_answers: list[str] = absent()


class TurnAnswer(Closed):
    by: str = absent()
    text: str = absent()
    special: Literal["not_sure_ask", "skip"] = absent()
    ask_sme_id: str = absent()


class CoverageAfter(Closed):
    percent: Confidence
    filled: list[str]
    unfilled: list[str]
    parked: list[str]


class Fork(Closed):
    from_process_id: str
    from_version: int
    to_process_id: str
    process_overrides: dict[str, Any]


class TimelineEntry(Closed):
    seq: Annotated[int, Field(ge=0)]
    kind: Literal["turn", "system_patch", "sme_answer", "phase_change", "playback", "signoff", "fork", "suggestions",
                  "suggestion_decision", "story_refinement"]
    turn: Annotated[str, Field(pattern=r"^T[0-9]+$")] = absent()
    phase: Phase
    at: DateTime = absent()
    target: TurnTarget = absent()
    question: TurnQuestion = absent()
    answer: TurnAnswer = absent()
    captured: list[str] = absent()
    assumptions: list[str] = absent()
    follow_up_question: str | None = absent()
    parked: list[str] = absent()
    question_id: str = absent()
    author: str = absent()
    ops: list[LooseOp] = absent()
    coverage_after: CoverageAfter = absent()
    playback_text: str = absent()
    from_phase: str = absent()
    to_phase: str = absent()
    story_ids: list[str] = absent()
    patch_id: str = absent()
    ir_version_after: int = absent()
    process: Literal["as_is", "to_be"] = absent()
    fork: Fork = absent()
    suggestion_ids: list[str] = absent()
    suggestion_id: str = absent()
    decision: Literal["accepted", "rejected", "edited"] = absent()
    story_id: str = absent()


class IntakeSession(Closed):
    session_id: Annotated[str, Field(pattern=r"^is_[a-z0-9_]{1,60}$")]
    process_id: ProcId
    requester_user_id: str
    source_id: SrcId = absent()
    idea_text: str
    phase: Phase
    status: Literal["active", "paused", "completed"]
    started_at: DateTime = absent()
    timeline: list[TimelineEntry]
    # Each item is a question.schema.json instance, validated separately (schema description).
    parked_questions: list[dict[str, Any]]
    final_coverage: Confidence
    stats: dict[str, Any] = absent()
    mode: Literal["idea", "as_is"]
    idea_id: str = absent()
    as_is_process_id: str | None = absent()
    to_be_process_id: str
