"""Story derivation (M7 rules 1-5 and the Story fields table). Port of tools/rs_reference.py::derive_stories.

Pure and deterministic: one story per live task, decisions/waits folded into their predecessor task (ir_core.graph).
"""
from ir_core.graph import adjacency, closure, live, story_groups, story_id_for
from ir_core.ids import collection_for

OPEN_GAP_STATUSES = frozenset({"open", "asked", "answered"})


def join_and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def lower_first(s: str) -> str:
    """'Cut the time…' → 'cut the time…'; acronyms ('KYC…') keep their case."""
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def handling_text(ir: dict, exception: dict) -> str:
    h = exception["handling"]
    action = h["action"]
    if action == "route_to_node":
        text = f"go to '{ir['nodes'][h['target_node_id']]['name']}'"
    elif action == "undefined":
        text = "UNDEFINED"
    else:
        text = action.replace("_", " ")
    if h.get("notify_actor_id"):
        text += f"; notify {ir['actors'][h['notify_actor_id']]['name']}"
    return text


def gap_target_ids(gap: dict) -> set[str]:
    return {r.split("/")[2] for r in gap["target_refs"] if len(r.split("/")) > 2}


def story_confidence(ir: dict, closure_ids: set[str], open_gaps: list[dict]) -> float:
    """IR §8.2: min confidence over the closure − 0.1 per open blocking gap − 0.03 per open major gap, floored at 0."""
    lowest = min(ir[collection_for(i)][i]["meta"]["confidence"] for i in closure_ids)
    blocking = sum(g["severity"] == "blocking" for g in open_gaps)
    major = sum(g["severity"] == "major" for g in open_gaps)
    return round(max(0.0, lowest - 0.1 * blocking - 0.03 * major), 3)


def derive_stories(ir: dict, gaps: list[dict], questions: list[dict] = (), version: int | None = None) -> dict:
    """The `stories` map for `ir` (stories with dor_status 'not_ready'; evaluate_dor sets the real status).

    `questions` (M6) name who each open gap is waiting on. `version` sets rendered_from_version.
    """
    nodes, groups = ir["nodes"], story_groups(ir)
    if no_actor := sorted(t for t in groups if nodes[t]["type"] == "task" and not nodes[t].get("actor_id")):
        # A story needs `as_a` (schema); M5 raises node_without_actor for these until the requester names someone.
        raise ValueError(f"cannot derive stories: tasks without an actor: {', '.join(no_actor)}")
    owner_of = {n: story_id_for(t) for t, ns in groups.items() for n in ns}
    adj = adjacency(ir)
    radj: dict[str, set[str]] = {}
    for a, bs in adj.items():
        for b in bs:
            radj.setdefault(b, set()).add(a)
    asked_to = {g: q["sme_id"] for q in questions for g in q["gap_ids"]
                if q.get("status") not in ("answered", "expired")}
    goals, live_goals, live_nfrs = ir.get("goals", {}), live(ir, "goals"), live(ir, "nfrs")
    out = {}
    for t, ns in groups.items():
        if nodes[t]["type"] != "task":
            continue
        sid, n, cl = story_id_for(t), nodes[t], closure(ir, ns)
        goal_ids = sorted({g for x in ns for g in nodes[x].get("goal_ids", []) if g in live_goals})
        statements = [lower_first(goals[g]["statement"]) for g in goal_ids]
        outcome = n.get("outcome")
        if outcome and statements:
            so_that = f"{outcome}, helping us {join_and(statements)}"
        elif statements:
            so_that = f"we can {join_and(statements)}"
        else:
            so_that = outcome or "the next step can proceed"

        acs = sorted(a for a in cl if a.startswith("ac_"))
        edge_cases = [{"ref": x, "title": ir["exceptions"][x]["name"],
                       "handling": handling_text(ir, ir["exceptions"][x])}
                      for x in sorted(i for i in cl if i.startswith("exc_"))]
        edge_cases += [{"ref": a, "title": ir["acceptance_criteria"][a]["title"],
                        "handling": "see acceptance criterion"}
                       for a in acs
                       if ir["acceptance_criteria"][a].get("kind", "happy_path") in ("edge_case", "negative")]
        nfr_ids = sorted(k for k, v in live_nfrs.items() if not v["applies_to"] or set(v["applies_to"]) & set(ns))

        access: dict[str, set[str]] = {}
        for x in ns:
            for e in nodes[x].get("inputs", []):
                access.setdefault(e, set()).add("read")
            for e in nodes[x].get("outputs", []):
                access.setdefault(e, set()).add("write")
        data = [{"entity_id": e, "access": "read_write" if len(a) == 2 else next(iter(a)),
                 "attributes": [at["name"] for at in ir["entities"][e]["attributes"]]}
                for e, a in sorted(access.items())]

        up = sorted({owner_of[p] for x in ns for p in radj.get(x, ()) if p in owner_of and owner_of[p] != sid})
        down = sorted({owner_of[s] for x in ns for s in adj.get(x, ()) if s in owner_of and owner_of[s] != sid})
        systems = sorted({s for x in ns for s in nodes[x].get("system_ids", [])}
                         | {nodes[x]["actor_id"] for x in ns if nodes[x].get("actor_id")
                            and ir["actors"][nodes[x]["actor_id"]]["kind"] == "system"})

        h = n.get("hitl", {})
        queues = [{"exception_id": x, "actor_id": ir["exceptions"][x]["handling"].get("notify_actor_id")}
                  for x in sorted(i for i in cl if i.startswith("exc_"))
                  if ir["exceptions"][x]["handling"]["action"] in ("manual_review", "escalate")]
        human_control = {"mode": h.get("mode"), "actor_id": h.get("actor_id"), "trigger": h.get("trigger"),
                         "criteria": h.get("criteria"), "queues": queues}

        open_gaps = [g for g in gaps if g["status"] in OPEN_GAP_STATUSES and gap_target_ids(g) & cl]
        change = None
        if n.get("change"):
            change = {"kind": n["change"]["kind"], "suggestion_id": n["change"]["suggestion_id"],
                      "was": n["change"].get("was"),
                      "minutes_saved_per_case": n.get("as_is_effort", {}).get("minutes_per_case")}
        out[sid] = {
            "title": n["name"], "as_a": n["actor_id"],
            "i_want": lower_first(n.get("description", n["name"])).rstrip("."),
            "so_that": so_that, "priority": n.get("priority"), "goal_ids": goal_ids,
            "persona_ids": sorted({p for g in goal_ids for p in goals[g].get("persona_ids", [])}),
            "node_ids": ns, "ac_ids": acs, "edge_cases": edge_cases, "nfr_ids": nfr_ids, "data_requirements": data,
            "dependencies": {"upstream_story_ids": up, "downstream_story_ids": down, "system_actor_ids": systems},
            "open_questions": [{"gap_id": g["gap_id"], "text": g["question"]["text"], "severity": g["severity"],
                                "status": g["status"], "asked_to": asked_to.get(g["gap_id"])} for g in open_gaps],
            "human_control": human_control, "automation_hint": n.get("automation_hint", "unknown"),
            "change": change,
            "confidence": story_confidence(ir, cl, open_gaps), "dor_status": "not_ready",
            "open_gap_ids": [g["gap_id"] for g in open_gaps]}
        if version is not None:
            out[sid]["rendered_from_version"] = version
    return out
