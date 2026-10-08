"""Element confidence (docs/02 §8.1, M8). Pure functions; parity with tools/rs_reference.py is tested.

Only the arithmetic order matters for float parity: keep the product over supporting refs in provenance order.
"""
from ir_core.ids import ELEMENT_COLLECTIONS, INFERRED_SOURCE_ID, collection_for

# Default authority weight by source kind (docs/02 §8.1). Applied when a source is created (M1/M0/M6); scoring reads
# the weight stored on the source, so per-process overrides live in processes.settings.authority_weights.
DEFAULT_AUTHORITY_WEIGHTS = {
    "interview_answer": 0.9, "sop": 0.8, "document": 0.7, "transcript": 0.6, "spreadsheet": 0.6, "email": 0.5,
    "recording": 0.5, "manual": 0.7, "intake": 0.8,
}
INFERRED_WEIGHT = 0.3
CERTAINTY_CAP = 0.9
CONFIRMED_FLOOR = 0.95
CONFLICT_FACTOR = 0.5


def _weight(ir: dict, source_id: str) -> float:
    return INFERRED_WEIGHT if source_id == INFERRED_SOURCE_ID else ir["sources"][source_id]["authority_weight"]


def _evidence(ir: dict, meta: dict) -> float:
    p = 1.0
    for r in meta["provenance"]:
        if r["stance"] == "supports":
            p *= 1 - _weight(ir, r["source_id"]) * min(r["extraction_certainty"], CERTAINTY_CAP)
    return 1 - p


def _conflicted(meta: dict) -> bool:
    return any(r["stance"] == "contradicts" for r in meta["provenance"])


def score_meta(ir: dict, meta: dict) -> float:
    evidence = _evidence(ir, meta)
    if meta["status"] == "rejected":
        return 0.0
    if meta["status"] == "confirmed":
        return round(max(evidence, CONFIRMED_FLOOR), 3)
    return round(evidence * (CONFLICT_FACTOR if _conflicted(meta) else 1.0), 3)


def score_elements(ir: dict) -> dict:
    """Write meta.confidence on every element, in place, and return the IR."""
    for coll in ELEMENT_COLLECTIONS:
        for element in ir.get(coll, {}).values():
            element["meta"]["confidence"] = score_meta(ir, element["meta"])
    return ir


def explain(ir: dict, element_id: str) -> dict:
    """Breakdown for the UI tooltip (M8): which refs count, their weights and the factors applied."""
    coll = collection_for(element_id)
    if coll not in ELEMENT_COLLECTIONS or element_id not in ir.get(coll, {}):
        raise KeyError(element_id)
    meta = ir[coll][element_id]["meta"]

    def ref(r: dict) -> dict:
        sid = r["source_id"]
        title = "Inferred" if sid == INFERRED_SOURCE_ID else ir["sources"][sid]["title"]
        return {"source_id": sid, "source": title, "w": _weight(ir, sid),
                "c": min(r["extraction_certainty"], CERTAINTY_CAP)}

    conflict = 1.0 if meta["status"] == "confirmed" or not _conflicted(meta) else CONFLICT_FACTOR
    return {
        "element": element_id,
        "status": meta["status"],
        "supports": [ref(r) for r in meta["provenance"] if r["stance"] == "supports"],
        "contradicts": [ref(r) for r in meta["provenance"] if r["stance"] == "contradicts"],
        "evidence": round(_evidence(ir, meta), 3),
        "conflict_factor": conflict,
        "confidence": score_meta(ir, meta),
    }
