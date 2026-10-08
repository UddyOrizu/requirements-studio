"""M5 §E story-readiness detectors: failing DOR-12/13/15/16 checks, merged per type into one gap each.

Each check mirrors tools/rs_reference.py::evaluate_dor for the story built from a task's group (ir_core.graph).
"""
from ir_core.graph import closure, live, story_groups

from .findings import Finding


def approval_problems(ir: dict, nid: str) -> list[str]:
    """An approval gate needs an approver, criteria, and both 'approved' and 'rejected' outgoing edges."""
    h = ir["nodes"][nid].get("hitl", {})
    problems = []
    if not h.get("actor_id"):
        problems.append("no approver")
    if not h.get("criteria"):
        problems.append("no criteria")
    outs = {e.get("condition", {}).get("outcome") for e in live(ir, "edges").values() if e["from"] == nid}
    problems += [f"no '{o}' path" for o in ("approved", "rejected") if o not in outs]
    return problems


def story_checks(ir: dict) -> dict[str, dict[str, bool]]:
    """task id → {DOR-12, DOR-13, DOR-15, DOR-16-hitl, DOR-16-approval: passed?}."""
    nodes, goals = ir["nodes"], live(ir, "goals")
    acs = live(ir, "acceptance_criteria")
    out = {}
    for task, group in story_groups(ir).items():
        if nodes[task]["type"] != "task":
            continue
        cl = closure(ir, group)
        story_acs = [acs[a] for a in cl if a in acs]
        needs_edge = (any(nodes[x]["type"] in ("decision", "wait") for x in group)
                      or any(i.startswith("exc_") for i in cl)
                      or any(nodes[x].get("hitl", {}).get("mode") == "approval" for x in group))
        has_edge = any(a.get("kind", "happy_path") in ("edge_case", "negative") for a in story_acs)
        tasks = [x for x in group if nodes[x]["type"] == "task"]
        out[task] = {
            "DOR-12": any(g in goals for x in group for g in nodes[x].get("goal_ids", [])),
            "DOR-13": bool(nodes[task].get("priority")),
            "DOR-15": not needs_edge or has_edge,
            "DOR-16-hitl": all(nodes[x].get("hitl", {}).get("mode") for x in tasks),
            "DOR-16-approval": not any(nodes[x].get("hitl", {}).get("mode") == "approval" and approval_problems(ir, x)
                                       for x in tasks),
        }
    return out


STORY_GAPS = [  # (check, gap type, severity)
    ("DOR-12", "story_value_missing", "major"),
    ("DOR-13", "story_priority_missing", "major"),
    ("DOR-15", "story_edge_cases_missing", "major"),
    ("DOR-16-hitl", "hitl_undefined", "major"),
    ("DOR-16-approval", "approval_gate_incomplete", "blocking"),
]


def story_readiness(ir: dict, *, document_led: bool) -> list[Finding]:
    """One gap per failing check type, targeting every failing story's task.

    Document-led processes skip hitl_undefined: there the C16 coverage gap asks the same question (M5 §E).
    """
    checks = story_checks(ir)
    nodes, goals = ir["nodes"], live(ir, "goals")
    out = []
    for check, gap_type, severity in STORY_GAPS:
        if gap_type == "hitl_undefined" and document_led:
            continue
        failing = [t for t, c in checks.items() if not c[check]]
        if not failing:
            continue
        names = [nodes[t]["name"] for t in failing]
        context = {"names": ", ".join(f"'{n}'" for n in names),
                   "goal_options": [g["statement"] for g in goals.values()][:3]}
        if gap_type == "approval_gate_incomplete":
            gates = [x for t in failing for x in story_groups(ir)[t]
                     if nodes[x].get("hitl", {}).get("mode") == "approval" and approval_problems(ir, x)]
            context["names"] = ", ".join(f"'{nodes[g]['name']}' ({', '.join(approval_problems(ir, g))})"
                                         for g in gates)
        performers = sorted({nodes[t]["actor_id"] for t in failing if nodes[t].get("actor_id")})
        out.append(Finding(gap_type, severity, "story", [f"/nodes/{t}" for t in failing], context,
                           candidate_actor_ids=performers))
    return out
