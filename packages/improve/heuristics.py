"""M11 candidate heuristics: where today's manual work could be automated. Pure; one candidate per task at most.

The LLM (prompts/improve_suggest.md) words the candidates, picks evidence and proposes ops; it cannot remove them.
Heuristics are tried in this order, so the most specific signal decides a step's kind.
"""
import re
from dataclasses import asdict, dataclass, field

from ir_core.graph import live

EMAIL = re.compile(r"\b(e-?mail|chas\w*|phone)\b", re.I)
PER_ITEM = re.compile(r"\b(each|separately|one at a time|every \w+ (searched|checked))\b", re.I)
REKEYING = re.compile(r"\b(typ\w*|rekey\w*|re-key\w*|copied)\b", re.I)
BY_HAND = re.compile(r"\b(by hand|manual\w*)\b", re.I)
API = re.compile(r"\bAPI\b")


@dataclass
class Candidate:
    target: str  # node id
    kind: str  # suggestion.schema.json kind
    heuristic: str
    default_control: str
    minutes_per_case: float | None
    pain_points: list[str] = field(default_factory=list)
    confidence_hint: str = "normal"  # "low" for the approval heuristic

    @property
    def target_ref(self) -> str:
        return f"/nodes/{self.target}"

    def as_dict(self) -> dict:
        return {**asdict(self), "target_refs": [self.target_ref]}


def _text(ir: dict, actor_ids: list[str]) -> str:
    return " ".join(f"{ir['actors'][a]['name']} {ir['actors'][a].get('description', '')}"
                    for a in actor_ids if a in ir["actors"])


def _narrow_branch_approvals(ir: dict) -> set[str]:
    """Approval tasks reached from a table-rule decision outcome that one row decides on a single condition."""
    rules, edges = live(ir, "decision_rules"), live(ir, "edges").values()
    out = set()
    for e in edges:
        outcome = (e.get("condition") or {}).get("outcome")
        target = ir["nodes"].get(e["to"], {})
        if not outcome or target.get("hitl", {}).get("mode") != "approval":
            continue
        for rid in ir["nodes"][e["from"]].get("rule_ids", []):
            logic = rules.get(rid, {}).get("logic", {})
            if logic.get("kind") == "table" and any(
                    row["then"] == outcome and sum(c not in ("*", "-") for c in row["when"]) == 1
                    for row in logic["rows"]):
                out.add(e["to"])
    return out


def _rule(ir: dict, nid: str, n: dict, *, sla_targets: set, narrow: set, sme_answers) -> tuple | None:
    """(kind, heuristic, default control, confidence hint) for one task, or None."""
    rules = live(ir, "decision_rules")
    mode = n.get("hitl", {}).get("mode")
    pain_text = " ".join(n.get("as_is_effort", {}).get("pain_points", []))
    systems = n.get("system_ids", [])
    system_text = _text(ir, systems)
    if mode == "approval":
        return ("automate_step", "narrow_approval", "sample review", "low") if nid in narrow else None
    if mode != "human_task":
        return None
    if any(rules.get(r, {}).get("logic", {}).get("kind") in ("table", "expression") for r in n.get("rule_ids", [])):
        return "deterministic_rule", "rule_applied_by_hand", "keep downstream approvals", "normal"
    if PER_ITEM.search(pain_text):
        return "automate_with_review", "search_per_item", "human review on exceptions and possible matches", "normal"
    if nid in sla_targets:
        return "automate_step", "repetitive_chasing", "keep the escalation exception", "normal"
    if REKEYING.search(pain_text):
        return "add_integration", "rekeying_into_system_of_record", "none (logged writes)", "normal"
    if EMAIL.search(pain_text) or EMAIL.search(system_text):
        return "add_integration", "manual_handoff_by_email", "none, or keep existing exception", "normal"
    if systems and (BY_HAND.search(pain_text) or API.search(system_text) or any(API.search(a) for a in sme_answers)):
        return "automate_step", "manual_check_against_system", "human queue for failures", "normal"
    return None


def candidates(ir: dict, *, sme_answers: list[str] = ()) -> list[Candidate]:
    """Candidates for an as-is IR (or its fresh to-be copy), in the IR's node order."""
    sla_targets = {s["breach_action"].get("target_node_id") for s in live(ir, "slas").values()
                   if s["breach_action"]["action"] == "route_to_node"}
    narrow = _narrow_branch_approvals(ir)
    out = []
    for nid, n in live(ir, "nodes").items():
        if n["type"] != "task":
            continue
        if rule := _rule(ir, nid, n, sla_targets=sla_targets, narrow=narrow, sme_answers=sme_answers):
            kind, heuristic, control, hint = rule
            effort = n.get("as_is_effort", {})
            out.append(Candidate(nid, kind, heuristic, control, effort.get("minutes_per_case"),
                                 effort.get("pain_points", []), hint))
    return out
