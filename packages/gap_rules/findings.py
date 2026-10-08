"""A finding is what a detector reports; `to_gap` turns it into a gap.schema.json object."""
import hashlib
from dataclasses import dataclass, field

SEVERITY_WEIGHT = {"blocking": 10, "major": 4, "minor": 1}
OPEN_STATUSES = frozenset({"open", "asked", "answered"})


@dataclass
class Finding:
    type: str
    severity: str  # blocking | major | minor
    detector: str  # structural | conflict | story
    target_refs: list[str]  # JSON Pointers, e.g. /nodes/node_x
    # Values for the wording templates (texts.py): element names, missing outcomes, …
    context: dict = field(default_factory=dict)
    evidence: list[dict] | None = None
    candidate_actor_ids: list[str] = field(default_factory=list)


def fingerprint(gap_type: str, target_refs: list[str], coverage_slot: str | None = None) -> str:
    """M5: sha1(type + ('#' + coverage_slot if any) + '|' + '|'.join(sorted(target_refs)))."""
    key = gap_type + (f"#{coverage_slot}" if coverage_slot else "")
    return hashlib.sha1((key + "|" + "|".join(sorted(target_refs))).encode()).hexdigest()


def target_ids(target_refs: list[str]) -> set[str]:
    """Element ids named by target refs (/nodes/node_x/name → node_x); section refs like /nfrs name none."""
    return {parts[2] for parts in (r.split("/") for r in target_refs) if len(parts) > 2}
