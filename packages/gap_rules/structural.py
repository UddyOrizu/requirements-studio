"""M5 §A structural detectors and §B conflict detector. Pure functions of the IR."""
import re

from ir_core.graph import adjacency, end_nodes, live, reach, start_nodes
from ir_core.ids import ELEMENT_COLLECTIONS

from .findings import Finding

ENTITY_REF = re.compile(r"\b(ent_[a-z0-9_]{1,60})\.([a-z][a-z0-9_]*)\b")
LOW_CONFIDENCE = 0.5


def _actor_options(ir: dict, kinds=("human_role", "team")) -> list[str]:
    return sorted(a["name"] for a in live(ir, "actors").values() if a["kind"] in kinds)[:3]


def _performers(ir: dict, node_ids) -> list[str]:
    nodes = ir["nodes"]
    return sorted({a for n in node_ids if n in nodes
                   for a in (nodes[n].get("actor_id"), nodes[n].get("hitl", {}).get("actor_id")) if a})


def _wired_outcomes(ir: dict, node_id: str, rule_id: str) -> set[str]:
    return {e["condition"]["outcome"] for e in live(ir, "edges").values()
            if e["from"] == node_id and e.get("condition") and e["condition"].get("rule_id") in (rule_id, None)
            and "outcome" in e["condition"]}


def _unhandled_table_values(ir: dict, rule: dict) -> list[str]:
    """Enum values of a table rule's input attributes that no row covers (and no '*' row catches)."""
    logic = rule["logic"]
    if logic["kind"] != "table":
        return []
    missing = []
    for col, ref in enumerate(rule.get("inputs", [])):
        ent, attr = ref.split(".")
        spec = next((a for a in ir["entities"].get(ent, {}).get("attributes", []) if a["name"] == attr), None)
        if not spec or spec["type"] != "enum" or col >= len(logic["columns"]):
            continue
        cells = {row["when"][col] for row in logic["rows"] if col < len(row["when"])}
        if "*" in cells or "-" in cells:
            continue
        missing += [f"{ref}={v}" for v in spec.get("enum_values", []) if v not in cells]
    return missing


def structural(ir: dict) -> list[Finding]:
    out: list[Finding] = []
    nodes, rules = live(ir, "nodes"), live(ir, "decision_rules")
    node_options = sorted(n["name"] for n in nodes.values() if n["type"] in ("task", "decision", "wait"))[:3]

    for nid, n in nodes.items():
        if n["type"] == "task" and not n.get("actor_id"):
            out.append(Finding("node_without_actor", "blocking", "structural", [f"/nodes/{nid}"],
                               {"name": n["name"], "actor_options": _actor_options(ir)}))

    for nid, n in nodes.items():
        if n["type"] != "decision":
            continue
        branch_gap = False
        for rid in n.get("rule_ids", []):
            if rid not in rules:
                continue
            missing = sorted(set(rules[rid]["outcomes"]) - _wired_outcomes(ir, nid, rid))
            missing += _unhandled_table_values(ir, rules[rid])
            if missing:
                branch_gap = True
                out.append(Finding("decision_missing_branch", "blocking", "structural",
                                   [f"/decision_rules/{rid}", f"/nodes/{nid}"],
                                   {"node": n["name"], "missing": " or ".join(f"'{m}'" for m in missing)},
                                   candidate_actor_ids=_performers(ir, [nid])))
        # Exhaustive: the node has a rule and every rule outcome is wired (the rule always yields one of them).
        exhaustive = any(r in rules for r in n.get("rule_ids", [])) and not branch_gap
        has_default = any(e.get("is_default") for e in live(ir, "edges").values() if e["from"] == nid)
        if not has_default and not exhaustive and not branch_gap:
            out.append(Finding("decision_missing_default", "major", "structural", [f"/nodes/{nid}"],
                               {"node": n["name"]}))

    timeouts = {nid for x in live(ir, "exceptions").values() if x.get("trigger_kind") == "timeout"
                for nid in x["applies_to"]}
    for nid, n in nodes.items():  # same rule as DOR-05
        if n["type"] == "wait" and not n.get("sla_ids") and nid not in timeouts:
            out.append(Finding("wait_without_timeout", "blocking", "structural", [f"/nodes/{nid}"],
                               {"name": n["name"]}, candidate_actor_ids=_performers(ir, _predecessors(ir, nid))))

    adj, starts, ends = adjacency(ir), start_nodes(ir), end_nodes(ir)
    if starts:
        reachable = reach(adj, starts)
        for nid, n in nodes.items():
            if nid not in reachable:
                out.append(Finding("unreachable_node", "major", "structural", [f"/nodes/{nid}"],
                                   {"name": n["name"], "node_options": node_options}))
    if ends:
        for nid, n in nodes.items():
            if n["type"] != "end" and not reach(adj, [nid]) & ends:
                out.append(Finding("no_path_to_end", "blocking", "structural", [f"/nodes/{nid}"],
                                   {"name": n["name"], "node_options": node_options},
                                   candidate_actor_ids=_performers(ir, [nid])))

    entities = ir["entities"]

    def undefined(ref_ent: str, attr: str) -> bool:
        return ref_ent not in entities or attr not in {a["name"] for a in entities[ref_ent]["attributes"]}

    for rid, r in rules.items():
        for ref in r.get("inputs", []):
            ent, attr = ref.split(".")
            if undefined(ent, attr):
                out.append(Finding("undefined_entity_reference", "major", "structural", [f"/decision_rules/{rid}"],
                                   {"ref": ref, "entity": ent, "attribute": attr}))
    for aid, a in live(ir, "acceptance_criteria").items():
        refs = {m.groups() for line in a["given"] + a["when"] + a["then"] for m in ENTITY_REF.finditer(line)}
        for ent, attr in sorted(refs):
            if undefined(ent, attr):
                out.append(Finding("undefined_entity_reference", "major", "structural",
                                   [f"/acceptance_criteria/{aid}"],
                                   {"ref": f"{ent}.{attr}", "entity": ent, "attribute": attr}))

    for sid, s in live(ir, "slas").items():
        if s["breach_action"]["action"] == "undefined":
            out.append(Finding("sla_without_breach_action", "major", "structural", [f"/slas/{sid}"],
                               {"name": s["name"], "actor_options": _actor_options(ir)},
                               candidate_actor_ids=_performers(ir, s["applies_to"])))
    for xid, x in live(ir, "exceptions").items():
        if x["handling"]["action"] == "undefined":
            out.append(Finding("exception_without_handling", "major", "structural", [f"/exceptions/{xid}"],
                               {"name": x["name"], "trigger": _lower_first(x["trigger"])},
                               candidate_actor_ids=_performers(ir, x["applies_to"])))

    with_ac = {t for a in live(ir, "acceptance_criteria").values() for t in a["applies_to"]}
    for nid, n in nodes.items():
        if n["type"] in ("task", "decision") and nid not in with_ac:
            out.append(Finding("node_without_acceptance_criteria", "major", "structural", [f"/nodes/{nid}"],
                               {"name": n["name"]}, candidate_actor_ids=_performers(ir, [nid])))

    gating = {e["condition"]["rule_id"] for e in live(ir, "edges").values()
              if e.get("condition", {}).get("rule_id")}
    for rid in sorted(gating):
        if rid in rules and rules[rid]["logic"]["kind"] == "natural_language":
            deciders = [k for k, n in nodes.items() if rid in n.get("rule_ids", [])]
            out.append(Finding("natural_language_rule_gating_edge", "major", "structural", [f"/decision_rules/{rid}"],
                               {"name": rules[rid]["name"]},
                               candidate_actor_ids=_performers(ir, _predecessors(ir, *deciders))))
    return out


def conflicts(ir: dict) -> list[Finding]:
    """§B: an element with a contradicting source that nobody has confirmed yet."""
    out = []
    for coll in ELEMENT_COLLECTIONS:
        for eid, x in live(ir, coll).items():
            prov = x["meta"]["provenance"]
            contra = [p for p in prov if p["stance"] == "contradicts"]
            if not contra or x["meta"]["status"] == "confirmed":
                continue
            fields = {p.get("field") for p in contra}
            blocking = "actor_id" in fields or coll == "decision_rules" or (coll == "slas" and "duration" in fields)
            statements = [f"'{p['excerpt']}'" for p in prov if p.get("excerpt")]
            out.append(Finding(
                "conflicting_sources", "blocking" if blocking else "major", "conflict", [f"/{coll}/{eid}"],
                {"label": _label(ir, coll, eid) + (f" ({', '.join(sorted(f for f in fields if f))})"
                                                   if any(fields) else ""),
                 "statements": " vs ".join(statements),
                 "choice_options": [p["excerpt"] for p in prov if p.get("excerpt")][:3]},
                evidence=[{"source_id": p["source_id"], "locator": p["locator"]["value"], "excerpt": p["excerpt"]}
                          for p in prov if p.get("excerpt")],
                candidate_actor_ids=_performers(ir, [eid]) if coll == "nodes" else []))
    return out


def low_confidence(ir: dict, conflicted: set[str]) -> list[Finding]:
    """`meta.confidence < 0.5`, not rejected, and not already explained by a conflict (suppression rule)."""
    out = []
    for coll in ELEMENT_COLLECTIONS:
        for eid, x in live(ir, coll).items():
            if x["meta"]["confidence"] >= LOW_CONFIDENCE or eid in conflicted:
                continue
            on_decision = coll == "decision_rules" or (coll == "nodes" and x.get("type") == "decision")
            out.append(Finding("low_confidence_element", "major" if on_decision else "minor", "structural",
                               [f"/{coll}/{eid}"], {"label": _label(ir, coll, eid)},
                               candidate_actor_ids=_performers(ir, [eid]) if coll == "nodes" else []))
    return out


def _predecessors(ir: dict, *node_ids: str) -> list[str]:
    return sorted({e["from"] for e in live(ir, "edges").values() if e["to"] in node_ids})


def _label(ir: dict, coll: str, eid: str) -> str:
    x = ir[coll][eid]
    name = x.get("name") or x.get("title") or x.get("term") or x.get("statement") or eid
    return f"'{name}'"


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s
