"""SME question — mirrors schemas/question.schema.json (M6; also intake 'ask someone' parking)."""
from typing import Annotated, Any, Literal

from pydantic import Field

from .common import AnyNumber, Closed, DateTime, absent
from .gap import AnswerType


class Answer(Closed):
    answer_id: str = absent()
    text: str = absent()
    structured_value: Any = absent()
    answered_by: str = absent()
    answered_at: DateTime = absent()


class Question(Closed):
    question_id: Annotated[str, Field(pattern=r"^q_[a-z0-9_]{1,60}$")]
    process_id: str
    batch_id: str = absent()
    gap_ids: Annotated[list[str], Field(min_length=1)]
    sme_id: str
    routing_score: AnyNumber
    routing_reason: str = absent()
    channel: Literal["in_app", "email", "teams"]
    text: Annotated[str, Field(max_length=400)]
    context_snippet: Annotated[str, Field(max_length=600)] = absent()
    answer_type: AnswerType
    suggested_answers: list[str] = absent()
    status: Literal["queued", "sent", "reminded", "escalated", "answered", "expired"]
    sent_at: DateTime | None = absent()
    due_at: DateTime | None = absent()
    answer: Answer | None = absent()
    origin: Literal["gap_routing", "intake_ask_someone"] = "gap_routing"
    asked_by: str = absent()
