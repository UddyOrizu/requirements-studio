import copy

import jsonpatch
import pytest

from services.ir_store.policy import answer_confirmations, auto_accept_allows, review_decision, touched_elements
from tests.conftest import KYC, SAMPLES, load


def _patch(**kw):
    p = load(SAMPLES / "patch_example.json")
    return {**p, **kw}


def test_m3_touched_elements():
    ops = [{"op": "replace", "path": "/nodes/node_a/meta/status", "value": "x"},
           {"op": "add", "path": "/sources/src_x", "value": {}},
           {"op": "move", "from": "/glossary/term_a", "path": "/glossary/term_b"},
           {"op": "test", "path": "/actors/act_x", "value": 1}]
    assert touched_elements(ops) == {("nodes", "node_a"), ("glossary", "term_a"), ("glossary", "term_b")}


@pytest.mark.parametrize("author,auto,version,enabled,allows,want", [
    ("user", True, 5, False, False, "apply"),
    ("user", False, 5, False, False, "propose"),
    ("agent", True, 0, False, False, "apply"),  # first extraction draft
    ("agent", True, 3, False, True, "propose"),  # policy off by default
    ("agent", True, 3, True, True, "apply"),
    ("agent", True, 3, True, False, "propose"),
    ("agent", False, 3, True, True, "propose"),
])
def test_m3_review_decision(author, auto, version, enabled, allows, want):
    ir = load(SAMPLES / "ir_client_onboarding.json")
    patch = _patch(author={"kind": author, "id": "x"}, auto_apply=auto, interpretation_confidence=0.93)
    sme = "sme_priya_shah"
    got = review_decision(patch, ir, current_version=version, auto_accept_enabled=enabled,
                          answerer_id=sme, routed_sme_id=sme if allows else "sme_other")
    assert got == want


def test_m3_auto_accept_policy_conditions():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    ok = dict(answerer_id="sme_priya_shah", routed_sme_id="sme_priya_shah")
    patch = _patch()
    assert auto_accept_allows(patch, ir, **ok)
    assert not auto_accept_allows(patch, ir, answerer_id="sme_priya_shah", routed_sme_id="sme_tom_reed")
    assert not auto_accept_allows(patch, ir, answerer_id=None, routed_sme_id=None)
    assert not auto_accept_allows(_patch(interpretation_confidence=0.84), ir, **ok)
    assert not auto_accept_allows(_patch(ops=patch["ops"] + [{"op": "remove", "path": "/glossary/x"}]), ir, **ok)
    # An element already confirmed by someone else may not be changed by auto-accept.
    other = copy.deepcopy(ir)
    other["nodes"]["node_high_risk_approval"]["meta"].update(status="confirmed", confirmed_by="sme_tom_reed")
    assert not auto_accept_allows(patch, other, **ok)
    other["nodes"]["node_high_risk_approval"]["meta"]["confirmed_by"] = "sme_priya_shah"
    assert auto_accept_allows(patch, other, **ok)


def test_m3_answer_confirmations_on_samples():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    patch = load(SAMPLES / "patch_example.json")
    after = jsonpatch.apply_patch(ir, patch["ops"])
    assert answer_confirmations(ir, after, patch["ops"]) == ["act_mlro", "node_high_risk_approval"]

    session = load(KYC / "intake_session_kyc.json")
    irs = {"as_is": load(KYC / "ir_v0_empty.json")}
    for e in session["timeline"]:
        if e["kind"] == "fork":
            break
        if e.get("ops"):
            before = irs["as_is"]
            irs["as_is"] = jsonpatch.apply_patch(before, e["ops"])
            if e["kind"] == "sme_answer":
                assert answer_confirmations(before, irs["as_is"], e["ops"]) == ["act_screening_tool"]
