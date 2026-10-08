"""M11 guardrails, applied after the LLM: suggestions that break one are dropped and listed as "Not suggested".

1 protected approvals · 2 a human control for every automation · 3 verbatim evidence · 4 computed benefit ·
5 ops that dry-run through M3 and stay within the target's story.
"""
import copy
import re
from dataclasses import dataclass, field

from ir_core import PatchRejected, apply_patch
from ir_core.graph import live, story_groups

CHANGE_KIND = {"automated": "automated", "hitl_review": "automated_with_review"}


@dataclass
class Verdict:
    suggestion: dict | None  # None when dropped
    not_suggested: dict | None = None  # {target, reason}
    notes: list[str] = field(default_factory=list)


def protected_approvals(ir: dict) -> dict[str, str]:
    """Approval tasks whose approver is named in scope.out or scope.constraints → the scope line protecting them."""
    lines = ir["scope"]["out"] + ir["scope"]["constraints"]
    out = {}
    for nid, n in live(ir, "nodes").items():
        h = n.get("hitl", {})
        approver = ir["actors"].get(h.get("actor_id") or n.get("actor_id") or "", {}).get("name")
        if h.get("mode") == "approval" and approver:
            for line in lines:
                if re.search(rf"\b{re.escape(approver)}\b", line, re.I):
                    out[nid] = line
    return out


def cases_per_month(ir: dict) -> int | None:
    """From the volume NFR: its measure, else its statement (first number, e.g. '~150 clients/month')."""
    for nfr in live(ir, "nfrs").values():
        if nfr["category"] == "volume":
            for text in (nfr.get("measure", ""), nfr["statement"]):
                if m := re.search(r"\d[\d,]*", text):
                    return int(m.group().replace(",", ""))
    return None


def benefit(ir: dict, targets: list[str], cases: int | None, qualitative: str | None) -> dict:
    """Guardrail 4: hours_saved_per_month = minutes_saved_per_case × cases_per_month / 60, never guessed."""
    minutes = [ir["nodes"][t].get("as_is_effort", {}).get("minutes_per_case") for t in targets if t in ir["nodes"]]
    minutes = [m for m in minutes if m is not None]
    if not minutes or cases is None:
        out = {"minutes_saved_per_case": None, "cases_per_month": None, "hours_saved_per_month": None}
        if qualitative:
            out["qualitative"] = qualitative
        return out
    total = sum(minutes)
    return {"minutes_saved_per_case": total, "cases_per_month": cases,
            "hours_saved_per_month": round(total * cases / 60, 1)}


def verbatim(excerpt: str, locator: str, source_id: str | None, turn_answers: dict[str, str],
             source_texts: dict[str, list[str]]) -> bool:
    """Guardrail 3: an intake quote is in the cited turn's answer; any other quote is in its source's text."""
    if locator in turn_answers:
        return excerpt in turn_answers[locator]
    return any(excerpt in text for text in source_texts.get(source_id or "", []))


def _story_scope(ir: dict, targets: list[str]) -> set[str]:
    groups = story_groups(ir)
    return {n for t in targets for n in groups.get(t, [t])}


def _routes_failures_to_a_person(ir: dict, node: str) -> bool:
    """An exception that hands work to a person applies to the step, its story, or the step right after it."""
    nearby = _story_scope(ir, [node]) | {e["to"] for e in live(ir, "edges").values() if e["from"] == node}
    return any(x["handling"]["action"] in ("manual_review", "escalate") and set(x["applies_to"]) & nearby
               for x in live(ir, "exceptions").values())


def _ops_in_scope(ops: list[dict], allowed_nodes: set[str], created: set[str]) -> list[str]:
    bad = []
    for op in ops:
        parts = op["path"].split("/")
        coll, eid = parts[1], parts[2] if len(parts) > 2 else ""
        ok = ((coll == "nodes" and eid in allowed_nodes)
              or (coll in ("exceptions", "slas") and eid in created)
              or (coll == "actors" and parts[3:] == ["description"]))
        if not ok:
            bad.append(op["path"])
    return bad


def _downgrade_to_review(ops: list[dict], ir: dict, node: str) -> list[dict]:
    """An automated step with nowhere to send failures keeps a person reviewing its exceptions."""
    out = []
    for op in ops:
        if op["path"] == f"/nodes/{node}/hitl/mode" and op.get("value") == "automated":
            out.append({**op, "value": "hitl_review"})
            h = ir["nodes"][node].get("hitl", {})
            for key, value in (("actor_id", ir["nodes"][node].get("actor_id")), ("trigger", "on_exception")):
                if key not in h and value:
                    out.append({"op": "add", "path": f"/nodes/{node}/hitl/{key}", "value": value})
        else:
            out.append(op)
    return out


def check(s: dict, to_be: dict, *, protected: dict[str, str], cases: int | None, turn_answers: dict[str, str],
          source_texts: dict[str, list[str]], qualitative: str | None = None) -> Verdict:
    """Apply all guardrails to one suggestion (suggestion.schema.json shape, before ids are final)."""
    targets = [r.split("/")[2] for r in s["target_refs"] if r.startswith("/nodes/")]
    label = ", ".join(to_be["nodes"][t]["name"] for t in targets if t in to_be["nodes"]) or ", ".join(s["target_refs"])

    for t in targets:  # 1
        if t in protected:
            return Verdict(None, {"target": label, "reason": f"out of scope: {protected[t]}"})
    if not s.get("controls", "").strip():  # 2a
        return Verdict(None, {"target": label, "reason": "no human control stated"})

    kept = [e for e in s["evidence"] if verbatim(e["excerpt"], e["locator"], e.get("source_id"), turn_answers,
                                                 source_texts)]  # 3
    if not kept:
        return Verdict(None, {"target": label, "reason": "no verifiable evidence"})
    notes = [f"evidence removed (not verbatim): {e['excerpt']!r}" for e in s["evidence"] if e not in kept]
    s = {**s, "evidence": kept, "benefit": benefit(to_be, targets, cases, qualitative)}  # 4

    created = {op["path"].split("/")[2] for op in s["ops"] if op["op"] == "add" and op["path"].count("/") == 2
               and op["path"].split("/")[1] in ("exceptions", "slas")}
    if bad := _ops_in_scope(s["ops"], _story_scope(to_be, targets), created):  # 5 (scope)
        return Verdict(None, {"target": label, "reason": f"changes outside the step: {', '.join(bad)}"})
    try:
        after = apply_patch(to_be, {"patch_id": "dry_run", "process_id": to_be["process"]["id"],
                                    "base_version": to_be["process"]["version"], "ops": s["ops"],
                                    "author": {"kind": "user", "id": "dry_run"}, "reason": "dry run",
                                    "auto_apply": False, "status": "proposed"})  # 5 (dry run)
    except PatchRejected as e:
        return Verdict(None, {"target": label, "reason": f"the change would not validate: {e}"[:300]})

    for t in targets:  # 2b
        if (after["nodes"][t].get("hitl", {}).get("mode") == "automated" and s["kind"] == "automate_step"
                and not _routes_failures_to_a_person(after, t)):
            s = {**s, "kind": "automate_with_review", "ops": _downgrade_to_review(s["ops"], to_be, t)}
            notes.append(f"{t}: downgraded to automate_with_review (failures had no person to go to)")
    return Verdict(s, notes=notes)


def complete_ops(s: dict, to_be: dict, *, source_id: str, requester_id: str) -> list[dict]:
    """The accept patch: the suggestion's ops plus what accepting implies, when the ops don't already say it —
    node.change on each changed target, provenance citing the suggestion, and created elements confirmed."""
    ops = copy.deepcopy(s["ops"])
    paths = {op["path"] for op in ops}
    ref = {"source_id": source_id, "locator": {"kind": "suggestion", "value": s["suggestion_id"]},
           "excerpt": s["title"][:300], "stance": "supports", "extraction_certainty": 0.9}
    after = apply_patch(to_be, {"patch_id": "x", "process_id": to_be["process"]["id"],
                                "base_version": to_be["process"]["version"], "ops": ops,
                                "author": {"kind": "user", "id": requester_id}, "reason": "x", "auto_apply": True,
                                "status": "proposed"})
    changes, refs = [], []
    for t in (r.split("/")[2] for r in s["target_refs"] if r.startswith("/nodes/")):
        node = after["nodes"][t]
        if f"/nodes/{t}/change" not in paths and not node.get("change"):
            was = to_be["nodes"][t].get("hitl", {}).get("mode")
            kind = CHANGE_KIND.get(node.get("hitl", {}).get("mode"), "modified")
            change = {"kind": kind, "suggestion_id": s["suggestion_id"], **({"was": was} if was else {})}
            changes.append({"op": "add", "path": f"/nodes/{t}/change", "value": change})
        if not any(p["source_id"] == source_id and p["locator"].get("value") == s["suggestion_id"]
                   for p in node["meta"]["provenance"]):
            refs.append({"op": "add", "path": f"/nodes/{t}/meta/provenance/-", "value": ref})
    for op in ops:
        parts = op["path"].split("/")
        if op["op"] == "add" and len(parts) == 3 and parts[1] in ("exceptions", "slas"):
            meta = op["value"].setdefault("meta", {"status": "proposed", "confidence": 0.0, "provenance": [ref]})
            if meta["status"] != "confirmed":
                meta.update(status="confirmed", confirmed_by=requester_id)
    return [*changes, *ops, *refs]
