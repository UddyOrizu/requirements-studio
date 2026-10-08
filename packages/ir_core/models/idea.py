"""Idea — mirrors schemas/idea.schema.json (M12)."""
from typing import Literal

from .common import AnyNumber, Closed, DateTime, IdeaId, absent


class IdeaStats(Closed):
    stories: int = absent()
    stories_ready: int = absent()
    open_questions: int = absent()
    suggestions_accepted: int = absent()
    suggestions_rejected: int = absent()
    hours_saved_per_month: AnyNumber | None = absent()
    coverage: AnyNumber = absent()


class Idea(Closed):
    idea_id: IdeaId
    title: str
    summary: str
    owner_user_id: str
    status: Literal["discovering", "improving", "refining", "ready", "exported"]
    has_as_is: bool
    as_is_process_id: str | None = absent()
    to_be_process_id: str | None
    session_id: str
    tags: list[str] = absent()
    stats: IdeaStats = absent()
    created_at: DateTime
    updated_at: DateTime
