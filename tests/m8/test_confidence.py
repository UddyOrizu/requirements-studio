"""score_elements must match the oracle (CLAUDE.md rule 7) on every sample IR and every replayed intermediate IR."""
import copy
import importlib.util
import sys

import jsonpatch
import pytest

from confidence_dor import explain, score_elements, score_meta
from ir_core.ids import ELEMENT_COLLECTIONS
from tests.conftest import KYC, ROOT, SAMPLES, load

_spec = importlib.util.spec_from_file_location("rs_reference", ROOT / "tools" / "rs_reference.py")
R = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("rs_reference", R)
_spec.loader.exec_module(R)

SAMPLE_IRS = [SAMPLES / "ir_client_onboarding.json", KYC / "ir_v0_empty.json",
              KYC / "ir_client_kyc_as_is.json", KYC / "ir_client_kyc_to_be.json"]


def _replayed_irs():
    """Every intermediate IR of the KYC session (as-is and forked to-be), as validate_samples replays it."""
    session = load(KYC / "intake_session_kyc.json")
    irs = {"as_is": load(KYC / "ir_v0_empty.json"), "to_be": None}
    for e in session["timeline"]:
        v = e.get("process", "as_is")
        if e["kind"] == "fork":
            irs["to_be"] = copy.deepcopy(irs["as_is"])
            irs["to_be"]["process"].update(e["fork"]["process_overrides"])
        elif e.get("ops"):
            irs[v] = jsonpatch.apply_patch(irs[v], e["ops"])
            yield pytest.param(copy.deepcopy(irs[v]), id=f"seq{e['seq']}-{v}")


def _scores(ir) -> dict:
    return {(c, k): x["meta"]["confidence"] for c in ELEMENT_COLLECTIONS for k, x in ir[c].items()}


@pytest.mark.parametrize("path", SAMPLE_IRS, ids=lambda p: p.name)
def test_m8_score_elements_matches_oracle_on_samples(path):
    ir = load(path)
    ours = score_elements(copy.deepcopy(ir))
    oracle = R.score_all(copy.deepcopy(ir))
    assert _scores(ours) == _scores(oracle)
    # The samples store oracle-scored confidence, so scoring them is a no-op.
    assert ours == ir


@pytest.mark.parametrize("ir", list(_replayed_irs()))
def test_m8_score_elements_matches_oracle_on_replay(ir):
    assert _scores(score_elements(copy.deepcopy(ir))) == _scores(R.score_all(copy.deepcopy(ir)))


def test_m8_score_meta_matches_oracle_on_edge_cases():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    prov = ir["nodes"]["node_screening"]["meta"]["provenance"]
    contra = {**prov[0], "stance": "contradicts"}
    inferred = {"source_id": "src_inferred", "locator": {"kind": "none", "value": ""}, "stance": "supports",
                "extraction_certainty": 1.0}
    for status in ("proposed", "confirmed", "rejected", "superseded"):
        for p in ([], prov, prov + [contra], [inferred], [contra]):
            meta = {"status": status, "confidence": 0, "provenance": p}
            assert score_meta(ir, meta) == R.score_meta(ir, meta), (status, p)


def test_M8_AC_M8_1():
    """score_elements on the sample IR yields node_screening.meta.confidence = 0.834 (± 0.001)."""
    ir = load(SAMPLES / "ir_client_onboarding.json")
    for c in ELEMENT_COLLECTIONS:
        for x in ir[c].values():
            x["meta"]["confidence"] = 0.0
    assert score_elements(ir)["nodes"]["node_screening"]["meta"]["confidence"] == pytest.approx(0.834, abs=0.001)


def test_m8_explain_matches_spec_example():
    e = explain(load(SAMPLES / "ir_client_onboarding.json"), "node_screening")
    assert e["evidence"] == 0.834 and e["confidence"] == 0.834 and e["conflict_factor"] == 1.0
    assert [(s["w"], s["c"]) for s in e["supports"]] == [(0.8, 0.85), (0.6, 0.8)]
    assert e["contradicts"] == []
    with pytest.raises(KeyError):
        explain(load(SAMPLES / "ir_client_onboarding.json"), "node_missing")
