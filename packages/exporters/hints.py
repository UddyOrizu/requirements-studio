"""export.hints per task node for MOTHER (M9 "Transformations"). The rest of the MOTHER package arrives in P9."""
from ir_core.graph import live


def export_hints(ir: dict) -> dict[str, dict]:
    """{task id: {automation_hint, hitl, single_goal_statement, priority, goal_ids, system_ids,
    acceptance_criteria_ids, qc_rubric_seed}}. qc_rubric_seed = the `then` clauses of the task's ACs, which MOTHER
    turns into the QC agent's rubric."""
    goals, acs = live(ir, "goals"), live(ir, "acceptance_criteria")
    out = {}
    for nid, n in live(ir, "nodes").items():
        if n["type"] != "task":
            continue
        ac_ids = sorted(a for a, ac in acs.items() if nid in ac["applies_to"])
        goal_ids = [g for g in n.get("goal_ids", []) if g in goals]
        out[nid] = {"automation_hint": n.get("automation_hint", "unknown"), "hitl": n.get("hitl", {}),
                    "single_goal_statement": goals[goal_ids[0]]["statement"] if goal_ids else None,
                    "priority": n.get("priority"), "goal_ids": goal_ids, "system_ids": n.get("system_ids", []),
                    "acceptance_criteria_ids": ac_ids,
                    "qc_rubric_seed": [t for a in ac_ids for t in acs[a]["then"]]}
    return out
