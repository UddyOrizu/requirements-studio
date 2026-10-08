"""M5 deterministic detectors (§A structural, §B conflict, §E story readiness), priority, fingerprints, reconcile."""
import copy

import pytest

from confidence_dor import score_elements
from gap_rules import PriorityModel, detect_gaps, fingerprint, reconcile
from gap_rules.story import story_checks
from ir_core import apply_patch, validate_schema
from tests.conftest import KYC, SAMPLES, load
from tests.oracle import R, replayed_irs

DETERMINISTIC = ("structural", "conflict", "story")
REPLAYED = dict(replayed_irs())


def onboarding():
    return load(SAMPLES / "ir_client_onboarding.json")


def sample_gaps():
    return load(SAMPLES / "gaps_client_onboarding.json")


def by_fp(gaps):
    return {g["fingerprint"]: g for g in gaps}


# ---------------------------------------------------------------- acceptance tests

def test_M5_AC_M5_1():
    """Structural + conflict detectors produce exactly the deterministic gaps in the sample, matched by fingerprint."""
    detected = [g for g in detect_gaps(onboarding(), document_led=True) if g["detector"] in ("structural", "conflict")]
    want = [g for g in sample_gaps() if g["detector"] in ("structural", "conflict")]
    assert set(by_fp(detected)) == set(by_fp(want))
    for fp, g in by_fp(want).items():
        got = by_fp(detected)[fp]
        assert (got["type"], got["severity"], got["detector"]) == (g["type"], g["severity"], g["detector"])


def test_M5_AC_M5_2():
    """wait_without_timeout on node_wait_docs is blocking, asks what happens after N days, answer duration/choice."""
    [gap] = [g for g in detect_gaps(onboarding(), document_led=True) if g["type"] == "wait_without_timeout"]
    assert gap["target_refs"] == ["/nodes/node_wait_docs"] and gap["severity"] == "blocking"
    assert gap["question"]["answer_type"] in ("duration", "choice")
    assert "how long" in gap["question"]["text"].lower() and "what happens" in gap["question"]["text"].lower()


def test_M5_AC_M5_3():
    """Applying patch_example.json auto-resolves the conflicting_sources gap on node_high_risk_approval."""
    ir = onboarding()
    existing = sample_gaps()
    conflict = next(g for g in existing if g["type"] == "conflicting_sources")
    assert conflict["fingerprint"] in by_fp(detect_gaps(ir, document_led=True))

    after = score_elements(apply_patch(ir, load(SAMPLES / "patch_example.json")))
    detected = detect_gaps(after, document_led=True)
    assert conflict["fingerprint"] not in by_fp(detected)
    result = reconcile(existing, detected, patch_id="0192a8f4-6c1e-7b3a-9d2e-5f01c4a7b9e1")
    resolved = by_fp(result.resolved)
    assert resolved[conflict["fingerprint"]]["status"] == "resolved"
    assert resolved[conflict["fingerprint"]]["resolved_by_patch_id"] == "0192a8f4-6c1e-7b3a-9d2e-5f01c4a7b9e1"
    # The other deterministic gaps are untouched by this patch.
    assert set(resolved) == {conflict["fingerprint"]}
    assert result.opened == []


# ---------------------------------------------------------------- samples

def test_m5_story_gaps_match_sample():
    detected = by_fp(g for g in detect_gaps(onboarding(), document_led=True) if g["detector"] == "story")
    want = by_fp(g for g in sample_gaps() if g["detector"] == "story")
    assert set(detected) == set(want)
    assert "hitl_undefined" not in {g["type"] for g in detected.values()}  # C16 coverage gap asks instead


def test_m5_priorities_match_sample():
    """The priority formula reproduces every sample priority, including semantic and coverage gaps."""
    model = PriorityModel(onboarding())
    for g in sample_gaps():
        assert model.priority(g["severity"], g["target_refs"]) == g["priority"], g["gap_id"]
    for g in detect_gaps(onboarding(), document_led=True):
        assert g["priority"] == by_fp(sample_gaps())[g["fingerprint"]]["priority"]


def test_m5_fingerprints_match_oracle():
    for g in sample_gaps() + load(KYC / "gaps_client_kyc.json"):
        assert fingerprint(g["type"], g["target_refs"], g.get("coverage_slot")) == g["fingerprint"] == \
            R.gap_fingerprint(g)


KYC_LIFECYCLE = [g for g in load(KYC / "gaps_client_kyc.json") if g["detector"] in DETERMINISTIC]


@pytest.mark.parametrize("gap", KYC_LIFECYCLE, ids=lambda g: g["gap_id"])
def test_m5_kyc_gap_detected_until_its_resolving_patch(gap):
    """Replaying the KYC session: each deterministic sample gap is detected from the version it records until the
    version produced by its resolved_by_patch_id, and not after."""
    variant = "as_is" if gap["process_id"].endswith("_as_is") else "to_be"
    resolved_at = int(gap["resolved_by_patch_id"].rsplit("_v", 1)[1])

    def found(version):
        return gap["fingerprint"] in by_fp(detect_gaps(REPLAYED[f"{variant}@v{version}"]))

    assert all(found(v) for v in range(gap["ir_version_detected"], resolved_at))
    assert not found(resolved_at)
    detected = by_fp(detect_gaps(REPLAYED[f"{variant}@v{gap['ir_version_detected']}"]))[gap["fingerprint"]]
    assert (detected["type"], detected["severity"]) == (gap["type"], gap["severity"])


@pytest.mark.parametrize("gap", [g for g in KYC_LIFECYCLE if g["gap_id"] != "gap_await_no_timeout"],
                         ids=lambda g: g["gap_id"])
def test_m5_kyc_priorities_match_sample(gap):
    # gap_await_no_timeout records 91.7 (11 downstream nodes); the replayed IR has 10 at every version it is open.
    variant = "as_is" if gap["process_id"].endswith("_as_is") else "to_be"
    ir = REPLAYED[f"{variant}@v{gap['ir_version_detected']}"]
    assert by_fp(detect_gaps(ir))[gap["fingerprint"]]["priority"] == gap["priority"]


def test_m5_kyc_to_be_is_gap_free():
    """The final to-be has 9 ready stories: no deterministic gaps remain."""
    assert detect_gaps(load(KYC / "ir_client_kyc_to_be.json")) == []


@pytest.mark.parametrize("label", ["onboarding", *REPLAYED])
def test_m5_detected_gaps_are_schema_valid(label):
    ir = onboarding() if label == "onboarding" else REPLAYED[label]
    for g in detect_gaps(ir):
        assert validate_schema(g, "gap") == [], g["gap_id"]


def _tasks_have_actors(ir) -> bool:
    return all(n.get("actor_id") for n in ir["nodes"].values() if n["type"] == "task")


@pytest.mark.parametrize("label", ["onboarding", *(k for k, ir in REPLAYED.items() if _tasks_have_actors(ir))])
def test_m5_story_checks_match_oracle_dor(label):
    # The oracle derives stories only once every task has an actor (as-is v1-v5 are earlier than that).
    """§E gaps come from DOR-12/13/15/16; each check agrees with tools/rs_reference.py::evaluate_dor."""
    ir = onboarding() if label == "onboarding" else REPLAYED[label]
    base = copy.deepcopy(ir)
    base.pop("stories", None)
    stories = R.derive_stories(base, [])
    rows = {r["story_id"]: {c["check_id"]: c for c in r["checks"]} for r in R.evaluate_dor(base, stories, [])}
    for task, checks in story_checks(base).items():
        row = rows[R.story_id_for(task)]
        assert checks["DOR-12"] == row["DOR-12"]["passed"]
        assert checks["DOR-13"] == row["DOR-13"]["passed"]
        assert checks["DOR-15"] == row["DOR-15"]["passed"]
        assert (checks["DOR-16-hitl"] and checks["DOR-16-approval"]) == row["DOR-16"]["passed"]


# ---------------------------------------------------------------- each detector

def _types(ir, **kw):
    return {(g["type"], tuple(g["target_refs"]), g["severity"]) for g in detect_gaps(ir, **kw)}


def _new(ir, mutate, **kw):
    before = _types(ir, **kw)
    mutate(ir)
    return _types(ir, **kw) - before


def _meta():
    return {"status": "proposed", "confidence": 0.9, "provenance": []}


@pytest.mark.parametrize("mutate,want", [
    (lambda ir: ir["nodes"]["node_screening"].pop("actor_id"),
     ("node_without_actor", ("/nodes/node_screening",), "blocking")),
    (lambda ir: ir["nodes"].update(node_orphan={"type": "task", "name": "Orphan", "actor_id": "act_mlro",
                                                "meta": _meta()}),
     ("unreachable_node", ("/nodes/node_orphan",), "major")),
    (lambda ir: ir["nodes"].update(node_orphan={"type": "task", "name": "Orphan", "actor_id": "act_mlro",
                                                "meta": _meta()}),
     ("no_path_to_end", ("/nodes/node_orphan",), "blocking")),
    (lambda ir: next(iter(ir["acceptance_criteria"].values()))["then"].append("ent_client.shoe_size is stored"),
     ("undefined_entity_reference", (f"/acceptance_criteria/{next(iter(onboarding()['acceptance_criteria']))}",),
      "major")),
    (lambda ir: ir["decision_rules"]["rule_risk_rating"]["meta"].update(confidence=0.2),
     ("low_confidence_element", ("/decision_rules/rule_risk_rating",), "major")),
    (lambda ir: ir["actors"]["act_crm"]["meta"].update(confidence=0.2),
     ("low_confidence_element", ("/actors/act_crm",), "minor")),
])
def test_m5_structural_detectors(mutate, want):
    assert want in _new(onboarding(), mutate, document_led=True)


def test_m5_decision_without_rule_or_default_edge():
    def drop_rule_and_default(ir):
        ir["nodes"]["node_accept_decision"].pop("rule_ids")
        ir["edges"]["edge_accept_no"].pop("is_default")

    added = _new(onboarding(), drop_rule_and_default, document_led=True)
    assert ("decision_missing_default", ("/nodes/node_accept_decision",), "major") in added


def test_m5_default_edge_or_wired_rule_is_enough():
    ir = onboarding()
    ir["nodes"]["node_accept_decision"].pop("rule_ids")  # the is_default edge still covers it
    assert not any(g["type"] == "decision_missing_default" for g in detect_gaps(ir, document_led=True))


def test_m5_no_default_gap_while_a_branch_gap_is_open():
    gaps = detect_gaps(onboarding(), document_led=True)
    assert any(g["type"] == "decision_missing_branch" and "/nodes/node_risk_decision" in g["target_refs"]
               for g in gaps)
    assert not any(g["type"] == "decision_missing_default" for g in gaps)


def test_m5_no_low_confidence_gap_for_a_conflicted_element():
    gaps = detect_gaps(onboarding(), document_led=True)
    node = onboarding()["nodes"]["node_high_risk_approval"]
    assert node["meta"]["confidence"] < 0.5
    assert not any(g["type"] == "low_confidence_element" and g["target_refs"] == ["/nodes/node_high_risk_approval"]
                   for g in gaps)


def test_m5_conflict_gap_carries_the_excerpts():
    [g] = [g for g in detect_gaps(onboarding(), document_led=True) if g["type"] == "conflicting_sources"]
    assert {e["source_id"] for e in g["evidence"]} == {"src_sop_onboarding_v4", "src_workshop_2026_09_24"}
    assert "Engagement Partner" in g["question"]["text"] and "MLRO" in g["question"]["text"]


def test_m5_conflict_severity_major_for_other_fields():
    ir = onboarding()
    ir["nodes"]["node_high_risk_approval"]["meta"]["provenance"][1]["field"] = "description"
    [g] = [g for g in detect_gaps(ir, document_led=True) if g["type"] == "conflicting_sources"]
    assert g["severity"] == "major"


def test_m5_hitl_and_approval_gate_gaps():
    ir = load(KYC / "ir_client_kyc_to_be.json")
    gate = next(k for k, n in ir["nodes"].items() if n.get("hitl", {}).get("mode") == "approval")
    ir["nodes"][gate]["hitl"].pop("criteria")  # schema requires it; DOR-16 checks it too
    ir["nodes"]["node_record_kyc"].pop("hitl")
    found = {(g["type"], g["severity"]) for g in detect_gaps(ir)}
    assert ("approval_gate_incomplete", "blocking") in found and ("hitl_undefined", "major") in found
    assert "hitl_undefined" not in {g["type"] for g in detect_gaps(ir, document_led=True)}


# ---------------------------------------------------------------- reconcile

def _gap(fp, status, detector="structural"):
    return {"gap_id": f"gap_{fp}", "fingerprint": fp, "status": status, "detector": detector}


def test_m5_reconcile_lifecycle():
    existing = [_gap("a", "open"), _gap("b", "answered"), _gap("c", "dismissed"), _gap("d", "resolved"),
                _gap("e", "open", detector="semantic"), _gap("f", "waived")]
    detected = [_gap("b", "open"), _gap("c", "open"), _gap("d", "open"), _gap("f", "open"), _gap("g", "open")]
    result = reconcile(existing, detected, patch_id="p9")
    assert [g["fingerprint"] for g in result.resolved] == ["a"]  # semantic gaps are never auto-resolved
    assert result.resolved[0]["resolved_by_patch_id"] == "p9"
    # Dismissed/waived stay closed; a resolved gap that reappears is a new gap.
    assert sorted(g["fingerprint"] for g in result.opened) == ["d", "g"]
