"""Referential integrity (docs/02 §9). Message text matches the oracle in tools/validate_samples.py."""
from .errors import Issue
from .ids import DEAD_STATUSES, ELEMENT_COLLECTIONS, INFERRED_SOURCE_ID, collection_for


def validate_integrity(ir: dict) -> list[Issue]:
    """Every referenced id exists and is live, plus the kind/outcome/attribute rules. Expects a schema-valid IR."""
    issues: list[Issue] = []

    def live(i: str) -> bool:
        coll = collection_for(i)
        return bool(coll) and i in ir.get(coll, {}) and ir[coll][i].get("meta", {}).get("status") not in DEAD_STATUSES

    def fail(coll: str, eid: str, message: str, ref: str | None = None):
        issues.append(Issue("integrity", f"/{coll}/{eid}", message, element_id=eid, ref_id=ref))

    def need(coll: str, eid: str, ref: str, where: str | None = None):
        if not live(ref):
            fail(coll, eid, f"{where or eid} references missing/rejected id '{ref}'", ref)

    for eid, e in ir["edges"].items():
        need("edges", eid, e["from"])
        need("edges", eid, e["to"])
        cond = e.get("condition")
        if cond and cond.get("rule_id"):
            rule = cond["rule_id"]
            need("edges", eid, rule)
            if cond.get("outcome") not in ir["decision_rules"].get(rule, {}).get("outcomes", []):
                fail("edges", eid, f"{eid} outcome '{cond.get('outcome')}' not in {rule}.outcomes", rule)

    for nid, n in ir["nodes"].items():
        if n.get("actor_id"):
            need("nodes", nid, n["actor_id"])
        for k in ("inputs", "outputs", "rule_ids", "sla_ids", "exception_ids", "goal_ids", "system_ids"):
            for ref in n.get(k, []):
                need("nodes", nid, ref, f"{nid}.{k}")
        if n.get("hitl", {}).get("actor_id"):
            need("nodes", nid, n["hitl"]["actor_id"], f"{nid}.hitl")
        for s in n.get("system_ids", []):
            if s in ir["actors"] and ir["actors"][s]["kind"] != "system":
                fail("nodes", nid, f"{nid}.system_ids {s} is not a system actor", s)

    for rid, r in ir["decision_rules"].items():
        for ref in r.get("inputs", []):
            ent, attr = ref.split(".")
            need("decision_rules", rid, ent)
            if ent in ir["entities"] and attr not in {a["name"] for a in ir["entities"][ent]["attributes"]}:
                fail("decision_rules", rid, f"{rid} input {ref} attribute undefined", ref)

    for coll in ("exceptions", "slas", "acceptance_criteria", "nfrs"):
        for xid, x in ir[coll].items():
            for ref in x["applies_to"]:
                need(coll, xid, ref)
    for coll, field in (("exceptions", "handling"), ("slas", "breach_action")):
        for xid, x in ir[coll].items():
            for k in ("target_node_id", "notify_actor_id"):
                if x[field].get(k):
                    need(coll, xid, x[field][k])

    for gid, g in ir["goals"].items():
        for ref in g.get("persona_ids", []):
            need("goals", gid, ref)
    for pid, p in ir["personas"].items():
        if p.get("actor_id"):
            need("personas", pid, p["actor_id"])

    for coll in ELEMENT_COLLECTIONS:
        for xid, x in ir[coll].items():
            for p in x["meta"]["provenance"]:
                if p["source_id"] != INFERRED_SOURCE_ID and p["source_id"] not in ir["sources"]:
                    fail(coll, xid, f"{xid} provenance cites unknown source {p['source_id']}", p["source_id"])

    for sid, s in ir.get("stories", {}).items():
        need("stories", sid, s["as_a"])
        for ref in s["node_ids"] + s["ac_ids"] + s["goal_ids"] + s["persona_ids"] + s["nfr_ids"]:
            need("stories", sid, ref)

    return issues
