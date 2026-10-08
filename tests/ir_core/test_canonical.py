import json

from ir_core import canonical_json, dump, ir_hash
from ir_core.models import ProcessIR
from tests.conftest import SAMPLES, load


def _reverse_keys(o):
    if isinstance(o, dict):
        return {k: _reverse_keys(o[k]) for k in reversed(list(o))}
    if isinstance(o, list):
        return [_reverse_keys(x) for x in o]
    return o


def test_ir_core_canonical_json_format():
    assert canonical_json({"b": 1, "a": [1.5, "é", None]}) == '{"a":[1.5,"é",null],"b":1}'.encode()


def test_ir_core_hash_ignores_key_order_and_model_roundtrip():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    h = ir_hash(ir)
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    assert ir_hash(_reverse_keys(ir)) == h
    assert ir_hash(dump(ProcessIR.model_validate(ir))) == h
    assert ir_hash(ProcessIR.model_validate(ir)) == h


def test_ir_core_hash_includes_confidence():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    h = ir_hash(ir)
    ir["nodes"]["node_screening"]["meta"]["confidence"] = 0.5
    assert ir_hash(ir) != h


def test_ir_core_hash_distinguishes_int_and_float():
    assert ir_hash({"x": 1}) != ir_hash({"x": 1.0})


def test_ir_core_canonical_is_valid_json():
    ir = load(SAMPLES / "ir_client_onboarding.json")
    assert json.loads(canonical_json(ir)) == ir
