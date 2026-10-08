from dataclasses import dataclass, field

from .findings import OPEN_STATUSES, Finding, fingerprint
from .priority import PriorityModel
from .story import story_readiness
from .structural import conflicts, low_confidence, structural
from .texts import TOPIC, word

DETERMINISTIC_DETECTORS = frozenset({"structural", "conflict", "story"})


def detect_gaps(ir: dict, *, document_led: bool = False) -> list[dict]:
    """Every deterministic gap in `ir`, as gap.schema.json objects (status open), highest priority first.

    `document_led`: the process has no active intake session, so coverage gaps (M5 §D) ask about human controls
    and hitl_undefined is not raised.
    """
    conflict_findings = conflicts(ir)
    conflicted = {r.split("/")[2] for f in conflict_findings for r in f.target_refs}
    findings: list[Finding] = (structural(ir) + conflict_findings + low_confidence(ir, conflicted)
                               + story_readiness(ir, document_led=document_led))
    model = PriorityModel(ir)
    gaps = [_to_gap(ir, f, model) for f in findings]
    return sorted(gaps, key=lambda g: (-g["priority"], g["gap_id"]))


def _to_gap(ir: dict, f: Finding, model: PriorityModel) -> dict:
    fp = fingerprint(f.type, f.target_refs)
    gap = {
        "gap_id": f"gap_{f.type}_{fp[:8]}",
        "process_id": ir["process"]["id"],
        "fingerprint": fp,
        "type": f.type,
        "severity": f.severity,
        "detector": f.detector,
        "target_refs": f.target_refs,
        **word(f.type, f.context),
        "routing": {"topic_tags": [TOPIC[f.type]], "candidate_actor_ids": f.candidate_actor_ids},
        "priority": model.priority(f.severity, f.target_refs),
        "status": "open",
        "ir_version_detected": ir["process"]["version"],
        "resolved_by_patch_id": None,
    }
    if f.evidence:
        gap["evidence"] = f.evidence
    return gap


@dataclass
class Reconciliation:
    opened: list[dict] = field(default_factory=list)  # new gaps to insert
    resolved: list[dict] = field(default_factory=list)  # existing gaps, now status resolved


def reconcile(existing: list[dict], detected: list[dict], *, patch_id: str | None) -> Reconciliation:
    """Auto-resolve and dedupe after a scan (M5 Lifecycle).

    - An open/asked/answered gap from a deterministic detector whose fingerprint is no longer detected is resolved
      by `patch_id`.
    - A detected gap is new unless a gap with its fingerprint exists that is not resolved; dismissed and waived gaps
      are not re-opened while their targets are unchanged (same fingerprint).
    """
    current = {g["fingerprint"] for g in detected}
    active = {g["fingerprint"] for g in existing if g["status"] != "resolved"}
    result = Reconciliation()
    for g in existing:
        auto = g["status"] in OPEN_STATUSES and g["detector"] in DETERMINISTIC_DETECTORS
        if auto and g["fingerprint"] not in current:
            result.resolved.append({**g, "status": "resolved", "resolved_by_patch_id": patch_id})
    result.opened = [g for g in detected if g["fingerprint"] not in active]
    return result
