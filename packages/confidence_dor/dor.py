"""Definition of Ready, DOR-01..16 (M8). Port of tools/rs_reference.py::evaluate_dor; parity is tested.

evaluate_dor sets each story's dor_status in place and returns one report row per story.
"""
import hashlib

from ir_core import canonical_json
from ir_core.graph import closure, live
from ir_core.ids import DEAD_STATUSES, collection_for

READY_THRESHOLD = 0.80
MANDATORY_NFR = ("volume", "security", "audit")
WAIVABLE = frozenset({"DOR-03", "DOR-06", "DOR-07", "DOR-09", "DOR-10", "DOR-14", "DOR-15"})
OPEN_GAP_STATUSES = frozenset({"open", "asked", "answered"})


def band(confidence: float) -> str:
    return "green" if confidence >= 0.8 else "amber" if confidence >= 0.5 else "red"


def approval_problems(ir: dict, nid: str) -> list[str]:
    """An approval gate needs an approver, criteria, and both 'approved' and 'rejected' outgoing edges."""
    h = ir["nodes"][nid].get("hitl", {})
    problems = []
    if not h.get("actor_id"):
        problems.append(f"{nid}: approval gate has no approver")
    if not h.get("criteria"):
        problems.append(f"{nid}: approval gate has no criteria")
    outs = {e.get("condition", {}).get("outcome") for e in live(ir, "edges").values() if e["from"] == nid}
    for outcome in ("approved", "rejected"):
        if outcome not in outs:
            problems.append(f"{nid}: approval gate has no '{outcome}' path")
    return problems


def closure_hash(ir: dict, story: dict) -> str:
    """M8 sign-off: sha256 of the canonical JSON of the story closure (the elements, not just their ids)."""
    ids = closure(ir, story["node_ids"])
    return hashlib.sha256(canonical_json({i: ir[collection_for(i)][i] for i in sorted(ids)})).hexdigest()


def _gap_targets(g: dict) -> set[str]:
    return {r.split("/")[2] for r in g["target_refs"] if len(r.split("/")) > 2}


def evaluate_dor(ir: dict, stories: dict, gaps: list[dict], signoffs=(), waivers=()) -> list[dict]:
    """`signoffs`: story ids with a valid owner sign-off. `waivers`: [{story_id, check_id}] (waivable checks only)."""
    rows = []
    waived = {(w["story_id"], w["check_id"]) for w in waivers}
    edges = live(ir, "edges")
    for sid, s in stories.items():
        ns, cl = s["node_ids"], closure(ir, s["node_ids"])
        checks = []

        def add(cid, ok, msg, checks=checks):
            checks.append({"check_id": cid, "passed": bool(ok), "waivable": cid in WAIVABLE,
                           "message": "" if ok else msg})

        acs = [ir["acceptance_criteria"][a] for a in s["ac_ids"]]
        add("DOR-01", s["as_a"] and ir["actors"][s["as_a"]]["meta"]["status"] not in DEAD_STATUSES,
            "Story has no live actor.")
        add("DOR-02", any(a["given"] and a["when"] and a["then"] for a in acs),
            "No acceptance criteria with Given/When/Then.")
        add("DOR-03", all(a["then"] for a in acs), "An acceptance criterion has no observable Then.")

        bad = []
        for x in ns:
            if ir["nodes"][x]["type"] != "decision":
                continue
            wired = {e["condition"]["outcome"] for e in edges.values() if e["from"] == x and e.get("condition")}
            for r in ir["nodes"][x].get("rule_ids", []):
                rule = ir["decision_rules"][r]
                if set(rule["outcomes"]) - wired:
                    bad.append(f"{x}: outcome(s) {sorted(set(rule['outcomes']) - wired)} of {r} not wired")
                if rule["logic"]["kind"] == "natural_language":
                    bad.append(f"{r} is natural language")
        add("DOR-04", not bad, "; ".join(bad))

        waits = [x for x in ns if ir["nodes"][x]["type"] == "wait"]
        no_timeout = [w for w in waits if not ir["nodes"][w].get("sla_ids") and not any(
            e.get("trigger_kind") == "timeout" and w in e["applies_to"] for e in live(ir, "exceptions").values())]
        add("DOR-05", not no_timeout, f"Wait node(s) {no_timeout} have no timeout.")

        undefined = [i for i in cl if i.startswith("exc_") and ir["exceptions"][i]["handling"]["action"] == "undefined"]
        add("DOR-06", not undefined, f"Exception(s) {undefined} have undefined handling.")

        missing = []
        for r in (i for i in cl if i.startswith("rule_")):
            for ref in ir["decision_rules"][r].get("inputs", []):
                ent, attr = ref.split(".")
                if ent not in ir["entities"] or attr not in {a["name"] for a in ir["entities"][ent]["attributes"]}:
                    missing.append(ref)
        add("DOR-07", not missing, f"Undefined entity attributes: {missing}.")

        blocking = [g["gap_id"] for g in gaps
                    if g["status"] in OPEN_GAP_STATUSES and g["severity"] == "blocking" and _gap_targets(g) & cl]
        add("DOR-08", not blocking, f"Open blocking gap(s): {blocking}.")
        add("DOR-09", s["confidence"] >= READY_THRESHOLD,
            f"Story confidence {s['confidence']} is below {READY_THRESHOLD:.2f}; confirm low-confidence elements.")

        vague = [t["term"] for t in live(ir, "glossary").values() if t["ambiguous"] and not t.get("definition")
                 and any(t["term"].lower() in " ".join(a["given"] + a["when"] + a["then"]).lower() for a in acs)]
        add("DOR-10", not vague, f"Ambiguous term(s) in acceptance criteria: {vague}.")
        add("DOR-11", sid in signoffs, "No process owner sign-off at the current closure.")
        add("DOR-12", s["goal_ids"], "Story is not linked to a business goal (no real 'so that').")
        add("DOR-13", s["priority"], "Priority not set.")
        cats = {ir["nfrs"][n]["category"] for n in s["nfr_ids"]}
        add("DOR-14", set(MANDATORY_NFR) <= cats, f"Missing NFR categories: {sorted(set(MANDATORY_NFR) - cats)}.")

        needs_edge = (any(ir["nodes"][x]["type"] in ("decision", "wait") for x in ns)
                      or any(i.startswith("exc_") for i in cl)
                      or any(ir["nodes"][x].get("hitl", {}).get("mode") == "approval" for x in ns))
        has_edge = any(a.get("kind", "happy_path") in ("edge_case", "negative") for a in acs)
        add("DOR-15", not needs_edge or has_edge,
            "Story has a decision, wait or exception but no edge-case acceptance criterion.")

        hitl_problems = []
        for x in ns:
            if ir["nodes"][x]["type"] != "task":
                continue
            h = ir["nodes"][x].get("hitl", {})
            if not h.get("mode"):
                hitl_problems.append(f"{x}: human-in-the-loop mode not set")
            elif h["mode"] == "approval":
                hitl_problems += approval_problems(ir, x)
            elif h["mode"] == "hitl_review" and not h.get("actor_id"):
                hitl_problems.append(f"{x}: review step has no reviewer")
        add("DOR-16", not hitl_problems, "; ".join(hitl_problems))

        failed = [c for c in checks if not c["passed"]]
        if not failed:
            status = "ready"
        elif all(c["waivable"] and (sid, c["check_id"]) in waived for c in failed):
            status = "waived"
        else:
            status = "not_ready"
        s["dor_status"] = status
        lowest = sorted((ir[collection_for(i)][i]["meta"]["confidence"], i) for i in cl)[:2]
        rows.append({"story_id": sid, "status": status, "confidence": s["confidence"], "band": band(s["confidence"]),
                     "lowest_confidence_elements": [{"id": i, "confidence": c} for c, i in lowest],
                     "failed_checks": [c["check_id"] for c in failed], "checks": checks})
    return rows


def process_ready(rows: list[dict]) -> bool:
    """M8: a process is ready when every story is ready or waived."""
    return all(r["status"] in ("ready", "waived") for r in rows)


def dor_report(ir: dict, stories: dict, gaps: list[dict], *, evaluated_at: str, signoffs=(), waivers=()) -> dict:
    """The full M8 report (samples/dor_report.json shape). Sets each story's dor_status in place."""
    rows = evaluate_dor(ir, stories, gaps, signoffs=set(signoffs), waivers=waivers)
    counts = {status: sum(r["status"] == status for r in rows) for status in ("ready", "waived", "not_ready")}
    return {"process_id": ir["process"]["id"], "ir_version": ir["process"]["version"], "evaluated_at": evaluated_at,
            "ready_threshold": READY_THRESHOLD, "mandatory_nfr_categories": list(MANDATORY_NFR),
            "summary": {"stories": len(rows), **counts}, "process_ready": process_ready(rows),
            "signoffs": sorted(signoffs), "stories": rows}
