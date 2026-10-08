"""M0 §1 coverage checklist and §2 Discover slot selection. Port of tools/rs_reference.py; parity is tested.

coverage() is normalised over the applicable slots: 17 in as-is mode (incl. C17 pain points), 16 in idea mode.
"""
from ir_core.graph import adjacency, live, reach

# Discovery order: (slot, key, weight, depends_on)
SLOTS = [
    ("C01", "goal", 0.08, ()), ("C04", "trigger", 0.07, ()), ("C05", "outcome", 0.07, ()),
    ("C02", "success_metric", 0.07, ()), ("C06", "happy_path", 0.10, ("C04", "C05")),
    ("C07", "actors", 0.07, ("C06",)), ("C08", "decisions", 0.07, ("C06",)), ("C13", "timing", 0.06, ("C06",)),
    ("C09", "exceptions", 0.07, ("C06",)), ("C10", "data", 0.06, ()), ("C11", "systems", 0.04, ()),
    ("C12", "volume", 0.05, ()), ("C14", "nfrs", 0.05, ()), ("C15", "scope", 0.04, ()),
    ("C03", "personas", 0.04, ()), ("C16", "human_controls", 0.06, ("C06", "C07")),
    ("C17", "pain_points", 0.06, ("C06",)),  # as-is only
]
AS_IS_ONLY = {"C17"}
SLOT_KEY = {s: k for s, k, _, _ in SLOTS}


def applicable(ir: dict, slot: str) -> bool:
    return slot not in AS_IS_ONLY or ir.get("process", {}).get("variant") == "as_is"


def slot_filled(ir: dict, slot: str) -> bool:
    nodes = live(ir, "nodes")
    tasks = {k: n for k, n in nodes.items() if n["type"] == "task"}
    none = set(ir.get("scope", {}).get("confirmed_none", []))
    nfr_categories = {n["category"] for n in live(ir, "nfrs").values()}
    match slot:
        case "C01":
            return bool(live(ir, "goals"))
        case "C02":
            return any(m.get("target") is not None for g in live(ir, "goals").values() for m in g["metrics"])
        case "C03":
            return bool(live(ir, "personas"))
        case "C04":
            return any(n["type"] == "start" and n.get("description") for n in nodes.values())
        case "C05":
            return any(n["type"] == "end" for n in nodes.values())
        case "C06":
            starts = [k for k, n in nodes.items() if n["type"] == "start"]
            ends = {k for k, n in nodes.items() if n["type"] == "end"}
            if len(tasks) < 3 or not starts or not ends:
                return False
            adj = adjacency(ir)
            forward = reach(adj, starts)
            body = [k for k, n in nodes.items() if n["type"] in ("task", "decision", "wait")]
            return all(k in forward and reach(adj, [k]) & ends for k in body)
        case "C07":
            return bool(tasks) and all(n.get("actor_id") for n in tasks.values())
        case "C08":
            rules = live(ir, "decision_rules")
            deterministic = any(
                n["type"] == "decision" and any(rules.get(r, {}).get("logic", {}).get("kind") in ("table", "expression")
                                                for r in n.get("rule_ids", []))
                for n in nodes.values())
            return deterministic or "decisions" in none
        case "C09":
            return bool(live(ir, "exceptions")) or "exceptions" in none
        case "C10":
            used = {e for n in nodes.values() for e in n.get("inputs", []) + n.get("outputs", [])}
            entities = live(ir, "entities")
            return bool(used) and all(e in entities and len(entities[e]["attributes"]) >= 2 for e in used)
        case "C11":
            return any(a["kind"] == "system" for a in live(ir, "actors").values()) or "systems" in none
        case "C12":
            return "volume" in nfr_categories
        case "C13":
            return bool(live(ir, "slas"))
        case "C14":
            return {"security", "audit"} <= nfr_categories
        case "C15":
            scope = ir.get("scope", {})
            return bool(scope.get("in")) and bool(scope.get("out"))
        case "C16":
            return bool(tasks) and all(n.get("hitl", {}).get("mode") for n in tasks.values())
        case "C17":
            return any(n.get("as_is_effort", {}).get("minutes_per_case") is not None for n in tasks.values())
    raise ValueError(f"unknown coverage slot {slot}")


def coverage(ir: dict, parked=()) -> dict:
    """{percent, filled, unfilled, parked}; percent is rounded to 2 places, parked slots count as 0."""
    slots = [x for x in SLOTS if applicable(ir, x[0])]
    filled = [s for s, *_ in slots if slot_filled(ir, s)]
    still_parked = [s for s in parked if s not in filled]
    unfilled = [s for s, *_ in slots if s not in filled and s not in still_parked]
    total = sum(w for _, _, w, _ in slots)
    percent = round(sum(w for s, _, w, _ in slots if s in filled) / total, 2)
    return {"percent": percent, "filled": filled, "unfilled": unfilled, "parked": still_parked}


def next_slot(ir: dict, parked=()) -> str | None:
    """First applicable slot in discovery order that is unfilled, not parked, with its dependencies filled."""
    filled = {s for s, *_ in SLOTS if applicable(ir, s) and slot_filled(ir, s)}
    for s, _, _, deps in SLOTS:
        if applicable(ir, s) and s not in filled and s not in parked and all(d in filled for d in deps):
            return s
    return None
