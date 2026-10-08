"""Patch review rules (docs/02 §7, M3, M6 §6). Pure functions over the patch envelope and IR dicts."""
from typing import Literal

from ir_core.ids import ELEMENT_COLLECTIONS

AUTO_ACCEPT_MIN_CONFIDENCE = 0.85


def touched_elements(ops: list[dict]) -> set[tuple[str, str]]:
    """(collection, id) of every IR element an op writes, e.g. /nodes/node_x/meta/status → ("nodes", "node_x")."""
    out = set()
    for op in ops:
        if op.get("op") == "test":
            continue
        for path in (op.get("path"), op.get("from") if op.get("op") == "move" else None):
            parts = (path or "").split("/")
            if len(parts) >= 3 and parts[1] in ELEMENT_COLLECTIONS:
                out.add((parts[1], parts[2]))
    return out


def _meta(ir: dict, coll: str, eid: str) -> dict | None:
    return ir.get(coll, {}).get(eid, {}).get("meta")


def answer_confirmations(before: dict, after: dict, ops: list[dict]) -> list[str]:
    """Ids of touched elements that the patch confirms (status → confirmed, or a new confirmed_by).

    M3: an answer patch must carry confirmation ops. The samples confirm the elements the answer is about, not every
    element touched (patch_example appends to an AC it leaves proposed), so at least one confirmation is required.
    """
    out = []
    for coll, eid in sorted(touched_elements(ops)):
        new, old = _meta(after, coll, eid), _meta(before, coll, eid) or {}
        if new and new["status"] == "confirmed" and (
            old.get("status") != "confirmed" or old.get("confirmed_by") != new.get("confirmed_by")
        ):
            out.append(eid)
    return out


def auto_accept_allows(patch: dict, ir: dict, *, answerer_id: str | None, routed_sme_id: str | None) -> bool:
    """M6 §6: all of — answerer is the routed SME; interpretation_confidence ≥ 0.85; only add/replace ops;
    no op changes an element already confirmed by someone else."""
    if not answerer_id or answerer_id != routed_sme_id:
        return False
    if patch.get("interpretation_confidence", 0) < AUTO_ACCEPT_MIN_CONFIDENCE:
        return False
    if any(op["op"] not in ("add", "replace") for op in patch["ops"]):
        return False
    for coll, eid in touched_elements(patch["ops"]):
        meta = _meta(ir, coll, eid)
        if meta and meta["status"] == "confirmed" and meta.get("confirmed_by") != answerer_id:
            return False
    return True


def review_decision(
    patch: dict,
    ir: dict,
    *,
    current_version: int,
    auto_accept_enabled: bool,
    answerer_id: str | None = None,
    routed_sme_id: str | None = None,
) -> Literal["apply", "propose"]:
    """docs/02 §7 rule 4: auto_apply is honoured for users and for the first extraction draft (version 0).
    Later agent patches are proposed unless the per-process auto-accept policy (default off) allows them."""
    if not patch["auto_apply"]:
        return "propose"
    if patch["author"]["kind"] == "user" or current_version == 0:
        return "apply"
    if auto_accept_enabled and auto_accept_allows(patch, ir, answerer_id=answerer_id, routed_sme_id=routed_sme_id):
        return "apply"
    return "propose"
