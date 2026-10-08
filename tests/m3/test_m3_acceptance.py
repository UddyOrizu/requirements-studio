"""M3 acceptance tests that P0 covers at the ir_core level.

The HTTP layer (POST /processes/{pid}/patches) arrives in P1; it maps PatchRejected straight to its status_code.
"""
import copy

import pytest

from ir_core import PatchRejected, apply_patch, canonical_json, ir_hash, validate_integrity, validate_schema
from tests.conftest import KYC, SAMPLES, load


def _patch(ops, base_version=3):
    return {
        "patch_id": "0192a8f4-0000-7000-8000-000000000001",
        "process_id": "proc_client_onboarding",
        "base_version": base_version,
        "ops": ops,
        "author": {"kind": "user", "id": "user_test"},
        "reason": "test",
        "auto_apply": True,
        "status": "proposed",
    }


def _edge(frm, to):
    return {"from": frm, "to": to,
            "meta": {"status": "proposed", "confidence": 0.5,
                     "provenance": [{"source_id": "src_inferred", "locator": {"kind": "none", "value": ""},
                                     "stance": "supports", "extraction_certainty": 0.5}]}}


def test_M3_AC_M3_2(onboarding_ir):
    """A patch adding an edge to a non-existent node returns 422 with an integrity error naming the id."""
    patch = _patch([{"op": "add", "path": "/edges/edge_to_nowhere",
                     "value": _edge("node_screening", "node_does_not_exist")}])
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, patch)
    rej = exc.value
    assert rej.status_code == 422
    integrity = [e for e in rej.errors if e.kind == "integrity"]
    assert integrity and any(e.ref_id == "node_does_not_exist" for e in integrity)
    assert "node_does_not_exist" in str(rej)


@pytest.mark.parametrize("op", [
    {"op": "add", "path": "/stories/story_new", "value": {}},
    {"op": "replace", "path": "/stories/story_screening/title", "value": "Rewritten"},
    {"op": "remove", "path": "/stories/story_screening"},
    {"op": "replace", "path": "/stories", "value": {}},
    {"op": "remove", "path": "/stories"},
    {"op": "move", "from": "/stories/story_screening", "path": "/glossary/term_x"},
    {"op": "copy", "from": "/nodes/node_screening", "path": "/stories/story_copy"},
    {"op": "test", "path": "/stories/story_screening/title", "value": "x"},
], ids=lambda o: f"{o['op']} {o.get('from', '')}{o['path']}")
def test_M3_AC_M3_4(onboarding_ir, op):
    """Any op targeting /stories/... returns 422."""
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, _patch([op]))
    assert exc.value.status_code == 422
    assert any(e.kind == "forbidden_path" for e in exc.value.errors)


@pytest.mark.parametrize("path", ["/process/version", "/process/updated_at"])
def test_M3_managed_process_fields_are_read_only(onboarding_ir, path):
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, _patch([{"op": "replace", "path": path, "value": 99}]))
    assert exc.value.status_code == 422


def test_M3_AC_M3_5():
    """Hash is stable: serialising the same IR twice yields the same sha256."""
    ir = load(SAMPLES / "ir_client_onboarding.json")
    assert canonical_json(ir) == canonical_json(copy.deepcopy(ir))
    assert ir_hash(ir) == ir_hash(copy.deepcopy(ir))
    to_be = load(KYC / "ir_client_kyc_to_be.json")
    assert ir_hash(to_be) == ir_hash(load(KYC / "ir_client_kyc_to_be.json"))
    assert ir_hash(to_be) != ir_hash(ir)


def test_ir_core_apply_patch_example(onboarding_ir, patch_example):
    """The sample patch applies cleanly (versioning and re-scoring for AC-M3-1 are the P1 Patch Service)."""
    before = copy.deepcopy(onboarding_ir)
    after = apply_patch(onboarding_ir, patch_example)
    assert onboarding_ir == before, "apply_patch must not mutate its input"
    node = after["nodes"]["node_high_risk_approval"]
    assert node["actor_id"] == "act_mlro" and node["meta"]["status"] == "confirmed"
    assert after["process"]["version"] == before["process"]["version"]
    assert validate_schema(after) == [] and validate_integrity(after) == []


def test_ir_core_apply_patch_schema_violation(onboarding_ir):
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, _patch([{"op": "replace", "path": "/nodes/node_screening/type", "value": "dance"}]))
    assert exc.value.status_code == 422
    assert any(e.kind == "schema" and e.path == "/nodes/node_screening/type" for e in exc.value.errors)


def test_ir_core_apply_patch_bad_op(onboarding_ir):
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, _patch([{"op": "remove", "path": "/nodes/node_not_there"}]))
    assert exc.value.status_code == 422
    assert exc.value.errors[0].kind == "patch_op"


def test_ir_core_apply_patch_test_op_failure(onboarding_ir):
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, _patch([{"op": "test", "path": "/process/name", "value": "Something else"}]))
    assert exc.value.errors[0].kind == "patch_op"


def test_ir_core_apply_patch_invalid_envelope(onboarding_ir):
    bad = _patch([{"op": "add", "path": "/glossary/term_x", "value": {}}])
    del bad["reason"]
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, bad)
    assert exc.value.errors[0].kind == "envelope"


def test_ir_core_apply_patch_wrong_process(onboarding_ir):
    bad = _patch([{"op": "add", "path": "/glossary/term_x", "value": {}}])
    bad["process_id"] = "proc_other"
    with pytest.raises(PatchRejected) as exc:
        apply_patch(onboarding_ir, bad)
    assert exc.value.errors[0].kind == "envelope"


@pytest.mark.parametrize("a,b,overlap", [
    ("/nodes/node_x", "/nodes/node_x/name", True),
    ("/nodes/node_x/name", "/nodes/node_x", True),
    ("/nodes/node_x", "/nodes/node_x", True),
    ("/nodes/node_x", "/nodes/node_xy", False),
    ("/nodes/node_x/name", "/nodes/node_y/name", False),
    ("/edges", "/edges/edge_a", True),
])
def test_ir_core_paths_overlap(a, b, overlap):
    from ir_core import paths_overlap
    assert paths_overlap(a, b) is overlap


def test_ir_core_changed_paths():
    from ir_core import changed_paths
    ops = [{"op": "move", "from": "/nodes/a", "path": "/nodes/b"}, {"op": "test", "path": "/x"},
           {"op": "replace", "path": "/nodes/c/name", "value": 1}, {"op": "add", "path": "/glossary/t/-", "value": 1}]
    assert changed_paths(ops) == ["/glossary/t", "/nodes/a", "/nodes/b", "/nodes/c/name"]
