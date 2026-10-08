"""Reference implementation of Requirements Studio's deterministic logic.

This is a TEST ORACLE, not production code. Production implementations live in
packages/confidence_dor, packages/story_renderer and services/intake, and must produce
identical results on the samples. Spec sources:
  confidence  -> docs/02-ir-specification.md §8
  coverage    -> docs/modules/M0-idea-intake-discovery.md §1-2
  stories     -> docs/modules/M7-story-renderer.md
  DoR         -> docs/modules/M8-confidence-dor.md
"""
from __future__ import annotations

import hashlib
import json
from collections import deque

ELEMENT_COLLS = ["actors", "entities", "nodes", "edges", "decision_rules", "exceptions", "slas",
                 "acceptance_criteria", "glossary", "goals", "personas", "nfrs"]
PREFIX = {"src": "sources", "act": "actors", "ent": "entities", "node": "nodes", "edge": "edges",
          "rule": "decision_rules", "exc": "exceptions", "sla": "slas", "ac": "acceptance_criteria",
          "term": "glossary", "story": "stories", "goal": "goals", "pers": "personas", "nfr": "nfrs"}
DEAD = {"rejected", "superseded"}
OPEN_GAP = {"open", "asked", "answered"}
MANDATORY_NFR = ("volume", "security", "audit")
READY_THRESHOLD = 0.80


def coll_of(eid: str) -> str:
    return PREFIX[eid.split("_")[0]]


def canonical(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(doc) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def gap_fingerprint(gap: dict) -> str:
    key = gap["type"] + (("#" + gap["coverage_slot"]) if gap.get("coverage_slot") else "")
    return hashlib.sha1((key + "|" + "|".join(sorted(gap["target_refs"]))).encode()).hexdigest()


def empty_ir(process_id: str, name: str, owner: str, updated_at: str, variant: str = "to_be", idea_id: str | None = None) -> dict:
    proc = {"id": process_id, "name": name, "owner_user_id": owner, "status": "draft", "version": 0,
            "updated_at": updated_at, "variant": variant}
    if idea_id:
        proc["idea_id"] = idea_id
    return {"ir_version": "1.1",
            "process": proc,
            "sources": {}, **{c: {} for c in ELEMENT_COLLS},
            "scope": {"in": [], "out": [], "assumptions": [], "constraints": [], "confirmed_none": []}}


def live(ir, coll):
    return {k: v for k, v in ir.get(coll, {}).items() if v.get("meta", {}).get("status") not in DEAD}


# ---------------------------------------------------------------- confidence (IR §8)
def _weight(ir, src):
    return 0.3 if src == "src_inferred" else ir["sources"][src]["authority_weight"]


def score_meta(ir, meta) -> float:
    p = 1.0
    for r in meta["provenance"]:
        if r["stance"] == "supports":
            p *= 1 - _weight(ir, r["source_id"]) * min(r["extraction_certainty"], 0.9)
    evidence = 1 - p
    if meta["status"] == "rejected":
        return 0.0
    if meta["status"] == "confirmed":
        return round(max(evidence, 0.95), 3)
    conflict = any(r["stance"] == "contradicts" for r in meta["provenance"])
    return round(evidence * (0.5 if conflict else 1.0), 3)


def score_all(ir):
    for c in ELEMENT_COLLS:
        for e in ir.get(c, {}).values():
            e["meta"]["confidence"] = score_meta(ir, e["meta"])
    return ir


# ---------------------------------------------------------------- graph
def adjacency(ir) -> dict[str, set[str]]:
    """Edges plus exception/SLA routes (route_to_node targets count as reachable)."""
    adj: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        adj.setdefault(e["from"], set()).add(e["to"])
    for x in live(ir, "exceptions").values():
        t = x["handling"].get("target_node_id")
        if x["handling"]["action"] == "route_to_node" and t:
            for n in x["applies_to"]:
                adj.setdefault(n, set()).add(t)
    for s in live(ir, "slas").values():
        t = s["breach_action"].get("target_node_id")
        if s["breach_action"]["action"] == "route_to_node" and t:
            for n in s["applies_to"]:
                adj.setdefault(n, set()).add(t)
    return adj


def reach(adj, starts) -> set[str]:
    seen, q = set(starts), deque(starts)
    while q:
        x = q.popleft()
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y); q.append(y)
    return seen


def bfs_distance(ir) -> dict[str, int]:
    """Flow distance from start: main-path edges first; nodes reached only via exception/SLA routes come after (+100)."""
    starts = [k for k, n in live(ir, "nodes").items() if n["type"] == "start"]

    def bfs(adj, seeds):
        dist = dict(seeds)
        q = deque(sorted(seeds, key=seeds.get))
        while q:
            x = q.popleft()
            for y in sorted(adj.get(x, ())):
                if y not in dist:
                    dist[y] = dist[x] + 1; q.append(y)
        return dist

    edge_adj: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        edge_adj.setdefault(e["from"], set()).add(e["to"])
    main = bfs(edge_adj, {s: 0 for s in starts})
    full = bfs(adjacency(ir), {s: 0 for s in starts})
    return {k: main.get(k, full[k] + 100) for k in full}


# ---------------------------------------------------------------- coverage (M0 §1)
SLOTS = [  # discovery order: (slot, key, weight, depends_on)
    ("C01", "goal", 0.08, ()), ("C04", "trigger", 0.07, ()), ("C05", "outcome", 0.07, ()),
    ("C02", "success_metric", 0.07, ()), ("C06", "happy_path", 0.10, ("C04", "C05")),
    ("C07", "actors", 0.07, ("C06",)), ("C08", "decisions", 0.07, ("C06",)), ("C13", "timing", 0.06, ("C06",)),
    ("C09", "exceptions", 0.07, ("C06",)), ("C10", "data", 0.06, ()), ("C11", "systems", 0.04, ()),
    ("C12", "volume", 0.05, ()), ("C14", "nfrs", 0.05, ()), ("C15", "scope", 0.04, ()), ("C03", "personas", 0.04, ()),
    ("C16", "human_controls", 0.06, ("C06", "C07")),
    ("C17", "pain_points", 0.06, ("C06",)),          # as-is only
]
AS_IS_ONLY = {"C17"}


def applicable(ir, slot) -> bool:
    return slot not in AS_IS_ONLY or ir.get("process", {}).get("variant") == "as_is"
SLOT_KEY = {s: k for s, k, _, _ in SLOTS}


def slot_filled(ir, slot) -> bool:
    nodes = live(ir, "nodes")
    tasks = {k: n for k, n in nodes.items() if n["type"] == "task"}
    none = set(ir.get("scope", {}).get("confirmed_none", []))
    nfr_cats = {n["category"] for n in live(ir, "nfrs").values()}
    if slot == "C01":
        return bool(live(ir, "goals"))
    if slot == "C02":
        return any(m.get("target") is not None for g in live(ir, "goals").values() for m in g["metrics"])
    if slot == "C03":
        return bool(live(ir, "personas"))
    if slot == "C04":
        return any(n["type"] == "start" and n.get("description") for n in nodes.values())
    if slot == "C05":
        return any(n["type"] == "end" for n in nodes.values())
    if slot == "C06":
        starts = [k for k, n in nodes.items() if n["type"] == "start"]
        ends = {k for k, n in nodes.items() if n["type"] == "end"}
        if len(tasks) < 3 or not starts or not ends:
            return False
        adj = adjacency(ir)
        fwd = reach(adj, starts)
        body = [k for k, n in nodes.items() if n["type"] in ("task", "decision", "wait")]
        return all(k in fwd and reach(adj, [k]) & ends for k in body)
    if slot == "C07":
        return bool(tasks) and all(n.get("actor_id") for n in tasks.values())
    if slot == "C08":
        rules = live(ir, "decision_rules")
        det = any(n["type"] == "decision" and any(rules.get(r, {}).get("logic", {}).get("kind") in ("table", "expression")
                                                   for r in n.get("rule_ids", [])) for n in nodes.values())
        return det or "decisions" in none
    if slot == "C09":
        return bool(live(ir, "exceptions")) or "exceptions" in none
    if slot == "C10":
        used = {e for n in nodes.values() for e in n.get("inputs", []) + n.get("outputs", [])}
        ents = live(ir, "entities")
        return bool(used) and all(e in ents and len(ents[e]["attributes"]) >= 2 for e in used)
    if slot == "C11":
        return any(a["kind"] == "system" for a in live(ir, "actors").values()) or "systems" in none
    if slot == "C12":
        return "volume" in nfr_cats
    if slot == "C13":
        return bool(live(ir, "slas"))
    if slot == "C14":
        return {"security", "audit"} <= nfr_cats
    if slot == "C16":
        return bool(tasks) and all(n.get("hitl", {}).get("mode") for n in tasks.values())
    if slot == "C17":
        return any(n.get("as_is_effort", {}).get("minutes_per_case") is not None for n in tasks.values())
    if slot == "C15":
        sc = ir.get("scope", {})
        return bool(sc.get("in")) and bool(sc.get("out"))
    raise ValueError(slot)


def coverage(ir, parked=()) -> dict:
    slots = [x for x in SLOTS if applicable(ir, x[0])]
    filled = [s for s, *_ in slots if slot_filled(ir, s)]
    pk = [s for s in parked if s not in filled]
    unfilled = [s for s, *_ in slots if s not in filled and s not in pk]
    total = sum(w for _, _, w, _ in slots)
    pct = round(sum(w for s, _, w, _ in slots if s in filled) / total, 2)
    return {"percent": pct, "filled": filled, "unfilled": unfilled, "parked": pk}


def next_slot(ir, parked=()) -> str | None:
    """Discover-phase selection (M0 §2, step 2). Follow-ups are handled by the caller."""
    filled = {s for s, *_ in SLOTS if applicable(ir, s) and slot_filled(ir, s)}
    for s, _, _, deps in SLOTS:
        if not applicable(ir, s):
            continue
        if s not in filled and s not in parked and all(d in filled for d in deps):
            return s
    return None


# ---------------------------------------------------------------- stories (M7)
def story_id_for(task_id: str) -> str:
    return "story_" + task_id.removeprefix("node_")


def story_groups(ir) -> dict[str, list[str]]:
    """task -> [task, folded decisions/waits]. Fold into the predecessor task nearest the start."""
    nodes = live(ir, "nodes")
    dist = bfs_distance(ir)
    preds: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        preds.setdefault(e["to"], set()).add(e["from"])
    groups = {k: [k] for k, n in nodes.items() if n["type"] == "task"}
    for k, n in sorted(nodes.items(), key=lambda kv: (dist.get(kv[0], 10**6), kv[0])):
        if n["type"] not in ("decision", "wait"):
            continue
        cands = [p for p in preds.get(k, ()) if nodes.get(p, {}).get("type") == "task"]
        if cands:
            owner = min(cands, key=lambda p: (dist.get(p, 10**6), p))
            groups[owner].append(k)
        else:
            groups[k] = [k]
    order = sorted(groups, key=lambda t: (dist.get(t, 10**6), t))
    return {t: groups[t] for t in order}


def closure(ir, node_ids) -> set[str]:
    ids = set(node_ids)
    for nid in node_ids:
        n = ir["nodes"][nid]
        if n.get("actor_id"):
            ids.add(n["actor_id"])
        for k in ("inputs", "outputs", "rule_ids", "sla_ids", "exception_ids", "goal_ids"):
            ids.update(n.get(k, []))
    for aid, a in live(ir, "acceptance_criteria").items():
        if set(a["applies_to"]) & set(node_ids):
            ids.add(aid)
    return ids


def _join(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _lower_first(s):
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _handling_text(ir, x):
    h = x["handling"]; a = h["action"]
    if a == "route_to_node":
        t = f"go to '{ir['nodes'][h['target_node_id']]['name']}'"
    elif a == "undefined":
        t = "UNDEFINED"
    else:
        t = a.replace("_", " ")
    if h.get("notify_actor_id"):
        t += f"; notify {ir['actors'][h['notify_actor_id']]['name']}"
    return t


def derive_stories(ir, gaps, questions=(), version=None) -> dict:
    nodes, groups = ir["nodes"], story_groups(ir)
    owner_of = {n: story_id_for(t) for t, ns in groups.items() for n in ns}
    adj = adjacency(ir)
    radj: dict[str, set[str]] = {}
    for a, bs in adj.items():
        for b in bs:
            radj.setdefault(b, set()).add(a)
    asked_to = {g: q["sme_id"] for q in questions for g in q["gap_ids"] if q.get("status") not in ("answered", "expired")}
    goals = ir.get("goals", {})
    out = {}
    for t, ns in groups.items():
        if nodes[t]["type"] != "task":
            continue
        sid, n, cl = story_id_for(t), nodes[t], closure(ir, ns)
        goal_ids = sorted({g for x in ns for g in nodes[x].get("goal_ids", []) if g in live(ir, "goals")})
        gstmts = [_lower_first(goals[g]["statement"]) for g in goal_ids]
        outcome = n.get("outcome")
        if outcome and gstmts:
            so_that = f"{outcome}, helping us {_join(gstmts)}"
        elif gstmts:
            so_that = f"we can {_join(gstmts)}"
        else:
            so_that = outcome or "the next step can proceed"
        acs = sorted(a for a in cl if a.startswith("ac_"))
        edge_cases = [{"ref": x, "title": ir["exceptions"][x]["name"], "handling": _handling_text(ir, ir["exceptions"][x])}
                      for x in sorted(i for i in cl if i.startswith("exc_"))]
        edge_cases += [{"ref": a, "title": ir["acceptance_criteria"][a]["title"], "handling": "see acceptance criterion"}
                       for a in acs if ir["acceptance_criteria"][a].get("kind", "happy_path") in ("edge_case", "negative")]
        nfr_ids = sorted(k for k, v in live(ir, "nfrs").items() if not v["applies_to"] or set(v["applies_to"]) & set(ns))
        access: dict[str, set[str]] = {}
        for x in ns:
            for e in nodes[x].get("inputs", []):
                access.setdefault(e, set()).add("read")
            for e in nodes[x].get("outputs", []):
                access.setdefault(e, set()).add("write")
        data = [{"entity_id": e, "access": "read_write" if len(a) == 2 else a.pop(),
                 "attributes": [at["name"] for at in ir["entities"][e]["attributes"]]} for e, a in sorted(access.items())]
        up = sorted({owner_of[p] for x in ns for p in radj.get(x, ()) if p in owner_of and owner_of[p] != sid})
        down = sorted({owner_of[s] for x in ns for s in adj.get(x, ()) if s in owner_of and owner_of[s] != sid})
        systems = sorted({s for x in ns for s in nodes[x].get("system_ids", [])} |
                         {nodes[x]["actor_id"] for x in ns if nodes[x].get("actor_id") and ir["actors"][nodes[x]["actor_id"]]["kind"] == "system"})
        h = n.get("hitl", {})
        queues = [{"exception_id": x, "actor_id": ir["exceptions"][x]["handling"].get("notify_actor_id")}
                  for x in sorted(i for i in cl if i.startswith("exc_"))
                  if ir["exceptions"][x]["handling"]["action"] in ("manual_review", "escalate")]
        human_control = {"mode": h.get("mode"), "actor_id": h.get("actor_id"), "trigger": h.get("trigger"),
                         "criteria": h.get("criteria"), "queues": queues}
        og = [g for g in gaps if g["status"] in OPEN_GAP and _gap_targets(g) & cl]
        conf_min = min(ir[coll_of(i)][i]["meta"]["confidence"] for i in cl)
        conf = round(max(0.0, conf_min - 0.1 * sum(g["severity"] == "blocking" for g in og)
                         - 0.03 * sum(g["severity"] == "major" for g in og)), 3)
        out[sid] = {
            "title": n["name"], "as_a": n["actor_id"], "i_want": _lower_first(n.get("description", n["name"])).rstrip("."),
            "so_that": so_that, "priority": n.get("priority"), "goal_ids": goal_ids,
            "persona_ids": sorted({p for g in goal_ids for p in goals[g].get("persona_ids", [])}),
            "node_ids": ns, "ac_ids": acs, "edge_cases": edge_cases, "nfr_ids": nfr_ids, "data_requirements": data,
            "dependencies": {"upstream_story_ids": up, "downstream_story_ids": down, "system_actor_ids": systems},
            "open_questions": [{"gap_id": g["gap_id"], "text": g["question"]["text"], "severity": g["severity"],
                                "status": g["status"], "asked_to": asked_to.get(g["gap_id"])} for g in og],
            "human_control": human_control, "automation_hint": n.get("automation_hint", "unknown"),
            "change": ({"kind": n["change"]["kind"], "suggestion_id": n["change"]["suggestion_id"], "was": n["change"].get("was"),
                        "minutes_saved_per_case": n.get("as_is_effort", {}).get("minutes_per_case")} if n.get("change") else None), "confidence": conf, "dor_status": "not_ready",
            "open_gap_ids": [g["gap_id"] for g in og]}
        if version is not None:
            out[sid]["rendered_from_version"] = version
    return out


def _gap_targets(g) -> set[str]:
    return {r.split("/")[2] for r in g["target_refs"] if len(r.split("/")) > 2}


# ---------------------------------------------------------------- DoR (M8)
WAIVABLE = {"DOR-03", "DOR-06", "DOR-07", "DOR-09", "DOR-10", "DOR-14", "DOR-15"}


def approval_problems(ir, nid) -> list[str]:
    """An approval gate needs an approver, criteria, and both 'approved' and 'rejected' outgoing edges."""
    h = ir["nodes"][nid].get("hitl", {})
    probs = []
    if not h.get("actor_id"):
        probs.append(f"{nid}: approval gate has no approver")
    if not h.get("criteria"):
        probs.append(f"{nid}: approval gate has no criteria")
    outs = {e.get("condition", {}).get("outcome") for e in live(ir, "edges").values() if e["from"] == nid}
    for o in ("approved", "rejected"):
        if o not in outs:
            probs.append(f"{nid}: approval gate has no '{o}' path")
    return probs


def evaluate_dor(ir, stories, gaps, signoffs=(), waivers=()) -> list[dict]:
    rows = []
    waived = {(w["story_id"], w["check_id"]) for w in waivers}
    for sid, s in stories.items():
        ns, cl = s["node_ids"], closure(ir, s["node_ids"])
        checks = []

        def add(cid, ok, msg):
            checks.append({"check_id": cid, "passed": bool(ok), "waivable": cid in WAIVABLE, "message": "" if ok else msg})

        acs = [ir["acceptance_criteria"][a] for a in s["ac_ids"]]
        add("DOR-01", s["as_a"] and ir["actors"][s["as_a"]]["meta"]["status"] not in DEAD, "Story has no live actor.")
        add("DOR-02", any(a["given"] and a["when"] and a["then"] for a in acs), "No acceptance criteria with Given/When/Then.")
        add("DOR-03", all(a["then"] for a in acs), "An acceptance criterion has no observable Then.")
        bad = []
        for x in ns:
            if ir["nodes"][x]["type"] != "decision":
                continue
            wired = {e["condition"]["outcome"] for e in live(ir, "edges").values() if e["from"] == x and e.get("condition")}
            for r in ir["nodes"][x].get("rule_ids", []):
                rule = ir["decision_rules"][r]
                if set(rule["outcomes"]) - wired:
                    bad.append(f"{x}: outcome(s) {sorted(set(rule['outcomes']) - wired)} of {r} not wired")
                if rule["logic"]["kind"] == "natural_language":
                    bad.append(f"{r} is natural language")
        add("DOR-04", not bad, "; ".join(bad))
        waits = [x for x in ns if ir["nodes"][x]["type"] == "wait"]
        no_to = [w for w in waits if not ir["nodes"][w].get("sla_ids") and not any(
            e.get("trigger_kind") == "timeout" and w in e["applies_to"] for e in live(ir, "exceptions").values())]
        add("DOR-05", not no_to, f"Wait node(s) {no_to} have no timeout.")
        undef = [i for i in cl if i.startswith("exc_") and ir["exceptions"][i]["handling"]["action"] == "undefined"]
        add("DOR-06", not undef, f"Exception(s) {undef} have undefined handling.")
        missing = []
        for r in (i for i in cl if i.startswith("rule_")):
            for ref in ir["decision_rules"][r].get("inputs", []):
                ent, attr = ref.split(".")
                if ent not in ir["entities"] or attr not in {a["name"] for a in ir["entities"][ent]["attributes"]}:
                    missing.append(ref)
        add("DOR-07", not missing, f"Undefined entity attributes: {missing}.")
        blk = [g["gap_id"] for g in gaps if g["status"] in OPEN_GAP and g["severity"] == "blocking" and _gap_targets(g) & cl]
        add("DOR-08", not blk, f"Open blocking gap(s): {blk}.")
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
        needs_edge = (any(ir["nodes"][x]["type"] in ("decision", "wait") for x in ns) or any(i.startswith("exc_") for i in cl)
                      or any(ir["nodes"][x].get("hitl", {}).get("mode") == "approval" for x in ns))
        has_edge = any(a.get("kind", "happy_path") in ("edge_case", "negative") for a in acs)
        add("DOR-15", not needs_edge or has_edge, "Story has a decision, wait or exception but no edge-case acceptance criterion.")
        hp = []
        for x in ns:
            if ir["nodes"][x]["type"] != "task":
                continue
            h = ir["nodes"][x].get("hitl", {})
            if not h.get("mode"):
                hp.append(f"{x}: human-in-the-loop mode not set")
            elif h["mode"] == "approval":
                hp += approval_problems(ir, x)
            elif h["mode"] == "hitl_review" and not h.get("actor_id"):
                hp.append(f"{x}: review step has no reviewer")
        add("DOR-16", not hp, "; ".join(hp))
        failed = [c for c in checks if not c["passed"]]
        if not failed:
            status = "ready"
        elif all(c["waivable"] and (sid, c["check_id"]) in waived for c in failed):
            status = "waived"
        else:
            status = "not_ready"
        s["dor_status"] = status
        lowest = sorted((ir[coll_of(i)][i]["meta"]["confidence"], i) for i in cl)[:2]
        rows.append({"story_id": sid, "status": status, "confidence": s["confidence"],
                     "band": "green" if s["confidence"] >= 0.8 else "amber" if s["confidence"] >= 0.5 else "red",
                     "lowest_confidence_elements": [{"id": i, "confidence": c} for c, i in lowest],
                     "failed_checks": [c["check_id"] for c in failed], "checks": checks})
    return rows
