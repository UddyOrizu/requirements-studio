"""M0 §2 next-question selection and the phase rules. Pure: decided from the IR, the session state and the gaps.

The LLM only phrases the chosen target (prompts/intake_phrase.md).
"""
from dataclasses import dataclass, field
from typing import Literal

from .coverage import coverage, next_slot

Phase = Literal["discover", "improve", "deepen", "validate", "done"]
DISCOVER_EXIT_COVERAGE = 0.80
DEEPEN_TYPES_EXCLUDED = {"story_value_missing", "story_priority_missing", "story_edge_cases_missing"}  # Validate's
VALIDATE_ORDER = ("story_priority_missing", "story_value_missing")


@dataclass
class SessionState:
    mode: Literal["idea", "as_is"]
    phase: Phase
    parked: list[str] = field(default_factory=list)  # slot ids, gap ids or playback targets parked this session
    follow_up_of: str | None = None  # turn label whose interpretation asked a follow-up, e.g. "T7"
    follow_up_question: str | None = None
    confirmed_playbacks: set[str] = field(default_factory=set)  # "as_is" / "to_be"


@dataclass(frozen=True)
class Target:
    kind: Literal["idea", "slot", "follow_up", "gap", "playback_confirm", "signoff", "phase"]
    id: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "id": self.id}


def _open(gaps: list[dict], parked: list[str]) -> list[dict]:
    return [g for g in gaps if g["status"] == "open" and g["gap_id"] not in parked]


def next_target(state: SessionState, ir: dict, gaps: list[dict]) -> Target:
    """The next thing to ask, or a phase change (Target kind 'phase', id = the phase to enter)."""
    if state.follow_up_of:
        return Target("follow_up", state.follow_up_of)
    if state.phase == "discover":
        slot = next_slot(ir, state.parked)
        if slot:
            return Target("slot", slot)
        if state.mode == "as_is":
            # Coverage complete: play the as-is back for confirmation before M11 improves it.
            if "as_is" not in state.confirmed_playbacks:
                return Target("playback_confirm", "as_is")
            return Target("phase", "improve")
        return Target("phase", "deepen")
    if state.phase == "improve":
        return Target("phase", "improve")  # waiting for M11: every suggestion decided
    if state.phase == "deepen":
        candidates = [g for g in _open(gaps, state.parked) if g["type"] not in DEEPEN_TYPES_EXCLUDED
                      and g["severity"] in ("blocking", "major")]
        if candidates:
            best = max(candidates, key=lambda g: (g["priority"], g["gap_id"]))
            return Target("gap", best["gap_id"])
        return Target("phase", "validate")
    if state.phase == "validate":
        open_gaps = _open(gaps, state.parked)
        for gap_type in VALIDATE_ORDER:
            for g in open_gaps:
                if g["type"] == gap_type:
                    return Target("gap", g["gap_id"])
        if "to_be" not in state.confirmed_playbacks:
            return Target("playback_confirm", "to_be")
        return Target("signoff", "all")
    return Target("phase", "done")


def discover_complete(ir: dict, state: SessionState) -> bool:
    """Discover may end: coverage ≥ 0.80 and no slot left to ask (every slot filled or parked)."""
    return next_slot(ir, state.parked) is None and coverage(ir, state.parked)["percent"] >= DISCOVER_EXIT_COVERAGE
