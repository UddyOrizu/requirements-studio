"""validate_integrity (docs/02 §9) must agree with the oracle check in tools/validate_samples.py."""
import importlib.util
import sys

import pytest

from ir_core import validate_integrity
from tests.conftest import KYC, ROOT, SAMPLES, load

_spec = importlib.util.spec_from_file_location("validate_samples", ROOT / "tools" / "validate_samples.py")
VS = importlib.util.module_from_spec(_spec)
sys.modules["validate_samples"] = VS
_spec.loader.exec_module(VS)


def oracle(ir) -> list[str]:
    VS.errors.clear()
    VS.integrity(ir, "x")
    out = [e.removeprefix("[integrity] x: ") for e in VS.errors]
    VS.errors.clear()
    return sorted(out)


def ours(ir) -> list[str]:
    return sorted(str(e) for e in validate_integrity(ir))


SAMPLE_IRS = [SAMPLES / "ir_client_onboarding.json", KYC / "ir_v0_empty.json",
              KYC / "ir_client_kyc_as_is.json", KYC / "ir_client_kyc_to_be.json"]


@pytest.mark.parametrize("path", SAMPLE_IRS, ids=lambda p: p.name)
def test_ir_core_integrity_samples_clean(path):
    ir = load(path)
    assert ours(ir) == oracle(ir) == []


def m_edge_to_missing_node(ir):
    ir["edges"]["edge_risk_low"]["to"] = "node_nowhere"


def m_actor_rejected(ir):
    ir["actors"]["act_onboarding_team"]["meta"]["status"] = "rejected"


def m_actor_superseded(ir):
    ir["actors"]["act_crm"]["meta"]["status"] = "superseded"


def m_system_id_not_system(ir):
    ir["nodes"]["node_screening"]["system_ids"] = ["act_mlro"]


def m_outcome_not_in_rule(ir):
    ir["edges"]["edge_risk_low"]["condition"]["outcome"] = "very_low"


def m_condition_rule_missing(ir):
    ir["edges"]["edge_risk_low"]["condition"]["rule_id"] = "rule_missing"


def m_rule_attribute_undefined(ir):
    ir["decision_rules"]["rule_risk_rating"]["inputs"].append("ent_client.shoe_size")


def m_rule_entity_missing(ir):
    ir["decision_rules"]["rule_risk_rating"]["inputs"].append("ent_missing.x")


def m_unknown_provenance_source(ir):
    n = next(n for n in ir["nodes"].values() if n["meta"]["provenance"])
    n["meta"]["provenance"][0]["source_id"] = "src_nowhere"


def m_exception_target_missing(ir):
    exc = next(x for x in ir["exceptions"].values() if x["handling"].get("target_node_id"))
    exc["handling"]["target_node_id"] = "node_gone"


def m_exception_applies_to_missing(ir):
    next(iter(ir["exceptions"].values()))["applies_to"].append("node_gone")


def m_sla_notify_missing(ir):
    next(iter(ir["slas"].values()))["breach_action"] = {"action": "notify", "notify_actor_id": "act_ghost"}


def m_ac_applies_to_missing(ir):
    next(iter(ir["acceptance_criteria"].values()))["applies_to"].append("nfr_ghost")


def m_node_inputs_and_goal_missing(ir):
    n = ir["nodes"]["node_screening"]
    n["inputs"] = n.get("inputs", []) + ["ent_ghost"]
    n["goal_ids"] = ["goal_ghost"]


def m_hitl_actor_missing(ir):
    n = next(n for n in ir["nodes"].values() if n.get("hitl", {}).get("actor_id"))
    n["hitl"]["actor_id"] = "act_ghost"


def m_goal_persona_and_persona_actor(ir):
    ir["goals"][next(iter(ir["goals"]))]["persona_ids"] = ["pers_ghost"]
    ir["personas"][next(iter(ir["personas"]))]["actor_id"] = "act_ghost"


def m_nfr_applies_to_missing(ir):
    next(iter(ir["nfrs"].values()))["applies_to"] = ["node_ghost"]


def m_story_refs_missing(ir):
    s = ir["stories"]["story_screening"]
    s["as_a"] = "act_ghost"
    s["ac_ids"].append("ac_ghost")


def m_node_removed_but_referenced(ir):
    del ir["nodes"]["node_screening"]


MUTATIONS = [m_edge_to_missing_node, m_actor_rejected, m_actor_superseded, m_system_id_not_system,
             m_outcome_not_in_rule, m_condition_rule_missing, m_rule_attribute_undefined, m_rule_entity_missing,
             m_unknown_provenance_source, m_exception_target_missing, m_exception_applies_to_missing,
             m_sla_notify_missing, m_ac_applies_to_missing, m_node_inputs_and_goal_missing, m_hitl_actor_missing,
             m_goal_persona_and_persona_actor, m_nfr_applies_to_missing, m_story_refs_missing,
             m_node_removed_but_referenced]


# The document-led sample has no hitl, personas or NFRs; these mutate the KYC to-be instead.
NEEDS_TO_BE = {m_hitl_actor_missing, m_goal_persona_and_persona_actor, m_nfr_applies_to_missing}


@pytest.mark.parametrize("mutate", MUTATIONS, ids=lambda f: f.__name__)
def test_ir_core_integrity_matches_oracle(mutate):
    ir = load(KYC / "ir_client_kyc_to_be.json" if mutate in NEEDS_TO_BE else SAMPLES / "ir_client_onboarding.json")
    mutate(ir)
    want = oracle(ir)
    assert want, "mutation should break integrity"
    assert ours(ir) == want


def test_ir_core_integrity_error_names_the_missing_id():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    m_edge_to_missing_node(ir)
    [err] = validate_integrity(ir)
    assert err.ref_id == "node_nowhere"
    assert err.element_id == "edge_risk_low"
    assert err.path == "/edges/edge_risk_low"
