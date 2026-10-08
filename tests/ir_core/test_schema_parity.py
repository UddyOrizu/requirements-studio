"""Pydantic ⇄ JSON Schema parity (CLAUDE.md rule 5).

Two halves:
1. Structural: walk every schema alongside its model and check property names, required sets, extra policy,
   enums/consts, nullability, patterns, numeric/length bounds, defaults and map key patterns.
2. Behavioural: conditional rules the walk can't see (if/then, allOf, oneOf) are checked by mutating valid samples
   and asserting the schema and the model both reject the result.
"""
import copy
import types
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError

from ir_core import validate_schema
from ir_core.models import MODEL_FOR_SCHEMA
from ir_core.models.common import check_date_time
from ir_core.schema import load_schema
from tests.conftest import KYC, SAMPLES, load

NoneType = type(None)


# ---------- annotation helpers ----------

def _unwrap(tp) -> tuple[Any, dict]:
    """Strip Annotated layers, collecting constraints (pattern, ge, le, min_length, max_length, date-time)."""
    cons: dict = {}
    while get_origin(tp) is Annotated:
        args = get_args(tp)
        tp = args[0]
        for m in args[1:]:
            _collect(m, cons)
    return tp, cons


def _collect(m, cons: dict) -> None:
    for attr in ("pattern", "ge", "le", "min_length", "max_length"):
        v = getattr(m, attr, None)
        if v is not None:
            cons[attr] = v
    if isinstance(m, AfterValidator) and m.func is check_date_time:
        cons["format"] = "date-time"
    for sub in getattr(m, "metadata", ()) or ():  # FieldInfo
        _collect(sub, cons)


def _field_type(field) -> tuple[Any, dict]:
    cons: dict = {}
    for m in field.metadata:
        _collect(m, cons)
    tp, inner = _unwrap(field.annotation)
    return tp, {**inner, **cons}


def _split_none(tp) -> tuple[list, bool]:
    if get_origin(tp) in (Union, types.UnionType):
        args = list(get_args(tp))
        return [a for a in args if a is not NoneType], NoneType in args
    return [tp], tp is NoneType


def _literal_values(tps: list) -> set | None:
    vals = set()
    for t in tps:
        t, _ = _unwrap(t)
        if get_origin(t) is not Literal:
            return None
        vals |= set(get_args(t))
    return vals


# ---------- the walker ----------

class Walker:
    def __init__(self, root_schema: dict):
        self.root = root_schema
        self.errors: list[str] = []

    def resolve(self, s: dict) -> dict:
        while "$ref" in s:
            name = s["$ref"].removeprefix("#/$defs/")
            s = self.root["$defs"][name]
        return s

    def err(self, path: str, msg: str):
        self.errors.append(f"{path}: {msg}")

    def model(self, s: dict, m: type[BaseModel], path: str):
        s = self.resolve(s)
        props = s.get("properties", {})
        fields = {(f.alias or n): f for n, f in m.model_fields.items()}
        if set(props) != set(fields):
            self.err(path, f"properties {sorted(set(props) ^ set(fields))} differ ({m.__name__})")
        required = set(s.get("required", []))
        model_required = {a for a, f in fields.items() if f.is_required()}
        if required != model_required:
            self.err(path, f"required: schema-only {required - model_required}, model-only {model_required - required}")
        extra = m.model_config.get("extra")
        want = "forbid" if s.get("additionalProperties") is False else "allow"
        if extra != want:
            self.err(path, f"{m.__name__} extra={extra!r}, schema implies {want!r}")
        for alias, f in fields.items():
            if alias not in props:
                continue
            ps = self.resolve(props[alias])
            if "default" in ps and f.default != ps["default"]:
                self.err(f"{path}/{alias}", f"default {f.default!r} != {ps['default']!r}")
            tp, cons = _field_type(f)
            self.value(ps, tp, cons, f"{path}/{alias}")

    def value(self, s: dict, tp, cons: dict, path: str):
        s = self.resolve(s)
        tps, nullable = _split_none(tp)
        st = s.get("type")
        schema_nullable = (isinstance(st, list) and "null" in st) or None in s.get("enum", [])
        if nullable != schema_nullable:
            self.err(path, f"nullable model={nullable} schema={schema_nullable}")
        if not s or set(s) <= {"description"}:  # {} = any value
            if tps != [Any]:
                self.err(path, f"schema allows anything, model has {tp}")
            return
        if "enum" in s or "const" in s:
            want = {v for v in s.get("enum", [s.get("const")]) if v is not None}
            got = _literal_values(tps)
            if got != want:
                self.err(path, f"enum model={got} schema={want}")
            return
        if "oneOf" in s:
            return self.one_of(s, tps, path)
        if len(tps) == 1:
            t, inner = _unwrap(tps[0])
            cons = {**inner, **cons}
        else:
            t = tps  # int | float
            for x in tps:
                cons = {**_unwrap(x)[1], **cons}
        kinds = [k for k in (st if isinstance(st, list) else [st]) if k != "null"]
        kind = kinds[0] if kinds else ("object" if "properties" in s else None)
        self.constraints(s, cons, path)
        if kind == "string":
            self.expect(t is str, path, f"string vs {t}")
        elif kind == "integer":
            self.expect(t is int, path, f"integer vs {t}")
        elif kind == "number":
            ok = isinstance(t, list) and {_unwrap(x)[0] for x in t} == {int, float}
            self.expect(ok, path, f"number must be int | float (keeps 1 and 1.0 distinct), got {t}")
        elif kind == "boolean":
            self.expect(t is bool, path, f"boolean vs {t}")
        elif kind == "array":
            self.expect(get_origin(t) is list, path, f"array vs {t}")
            if get_origin(t) is list:
                it, icons = _unwrap(get_args(t)[0])
                self.value(s.get("items", {}), it, icons, path + "/[]")
        elif kind == "object":
            self.object(s, t, path)
        else:
            self.err(path, f"unhandled schema {s}")

    def object(self, s: dict, t, path: str):
        if "properties" in s:
            if not (isinstance(t, type) and issubclass(t, BaseModel)):
                return self.err(path, f"object with properties vs {t}")
            return self.model(s, t, path)
        ap = s.get("additionalProperties")
        if isinstance(ap, dict):  # map keyed by id
            if get_origin(t) is not dict:
                return self.err(path, f"map vs {t}")
            kt, vt = get_args(t)
            _, kcons = _unwrap(kt)
            want = s.get("propertyNames", {}).get("pattern")
            if kcons.get("pattern") != want:
                self.err(path, f"key pattern {kcons.get('pattern')!r} != {want!r}")
            vt, vcons = _unwrap(vt)
            return self.value(ap, vt, vcons, path + "/{}")
        # open object: dict[str, Any], or a model whose required fields match and which allows extras
        if get_origin(t) is dict:
            if s.get("required"):
                self.err(path, "open object with required keys must be a model")
            return
        if isinstance(t, type) and issubclass(t, BaseModel):
            self.expect(t.model_config.get("extra") == "allow", path, f"{t.__name__} must allow extra")
            req = {f.alias or n for n, f in t.model_fields.items() if f.is_required()}
            self.expect(req == set(s.get("required", [])), path, f"required {req} != {s.get('required')}")
            return
        self.err(path, f"open object vs {t}")

    def one_of(self, s: dict, tps: list, path: str):
        variants = [self.resolve(v) for v in s["oneOf"]]
        if len(tps) == 1 and get_origin(tps[0]) in (Union, types.UnionType):
            tps = list(get_args(tps[0]))
        models = [_unwrap(t)[0] for t in tps]
        by_kind = {}
        for m in models:
            kind_t = m.model_fields["kind"].annotation
            by_kind[get_args(kind_t)[0]] = m
        for v in variants:
            k = v["properties"]["kind"]["const"]
            if k not in by_kind:
                self.err(path, f"oneOf variant {k} has no model")
            else:
                self.model(v, by_kind[k], f"{path}<{k}>")
        self.expect(len(by_kind) == len(variants), path, "extra union members")

    def constraints(self, s: dict, cons: dict, path: str):
        want = {"pattern": s.get("pattern"), "ge": s.get("minimum"), "le": s.get("maximum"),
                "min_length": s.get("minItems", s.get("minLength")),
                "max_length": s.get("maxItems", s.get("maxLength"))}
        want = {k: v for k, v in want.items() if v is not None}
        got = {k: v for k, v in cons.items() if k != "format"}
        if got != want:
            self.err(path, f"constraints schema {want} model {got}")
        if (s.get("format") == "date-time") != (cons.get("format") == "date-time"):
            self.err(path, "format date-time differs")

    def expect(self, cond: bool, path: str, msg: str):
        if not cond:
            self.err(path, msg)


@pytest.mark.parametrize("schema_name", sorted(MODEL_FOR_SCHEMA))
def test_ir_core_schema_parity_structure(schema_name):
    schema = load_schema(schema_name)
    w = Walker(schema)
    w.model(schema, MODEL_FOR_SCHEMA[schema_name], schema_name)
    assert w.errors == []


def test_ir_core_every_schema_has_a_model():
    from ir_core.schema import SCHEMA_DIR
    names = {p.name.removesuffix(".schema.json") for p in SCHEMA_DIR.glob("*.schema.json")}
    assert names == set(MODEL_FOR_SCHEMA)


# ---------- behavioural parity on invalid documents ----------

def _ir():
    return load(SAMPLES / "ir_client_onboarding.json")


def _first(d: dict) -> str:
    return next(iter(d))


def _task_with_hitl(ir):
    return next(k for k, n in ir["nodes"].items() if "hitl" in n)


def m_confirmed_without_by(ir):
    ir["actors"][_first(ir["actors"])]["meta"] = {"status": "confirmed", "confidence": 1, "provenance": []}


def m_approval_without_criteria(ir):
    ir["nodes"][_task_with_hitl(ir)]["hitl"] = {"mode": "approval", "actor_id": "act_mlro"}


def m_review_without_trigger(ir):
    ir["nodes"][_task_with_hitl(ir)]["hitl"] = {"mode": "hitl_review", "actor_id": "act_mlro"}


def m_logic_mixed_variants(ir):
    r = ir["decision_rules"][_first(ir["decision_rules"])]
    r["logic"] = {"kind": "expression", "expression": "x > 1", "text": "also natural language"}


def m_logic_unknown_kind(ir):
    ir["decision_rules"][_first(ir["decision_rules"])]["logic"] = {"kind": "dmn"}


def m_bad_map_key(ir):
    ir["nodes"]["Node_Bad"] = ir["nodes"].pop(_first(ir["nodes"]))


def m_bad_duration(ir):
    ir["slas"][_first(ir["slas"])]["duration"] = "5 days"


def m_empty_duration(ir):
    ir["slas"][_first(ir["slas"])]["duration"] = "P"


def m_bad_datetime(ir):
    ir["process"]["updated_at"] = "yesterday"


def m_null_optional(ir):
    ir["nodes"][_first(ir["nodes"])]["description"] = None


def m_extra_property(ir):
    ir["nodes"][_first(ir["nodes"])]["colour"] = "red"


def m_confidence_out_of_range(ir):
    ir["actors"][_first(ir["actors"])]["meta"]["confidence"] = 1.2


def m_missing_scope(ir):
    del ir["scope"]


def m_wrong_ir_version(ir):
    ir["ir_version"] = "1.0"


def m_excerpt_too_long(ir):
    n = next(n for n in ir["nodes"].values() if n["meta"]["provenance"])
    n["meta"]["provenance"][0]["excerpt"] = "x" * 301


NEEDS_HITL = {m_approval_without_criteria, m_review_without_trigger}  # the document-led IR has no hitl
IR_MUTATIONS = [m_confirmed_without_by, m_approval_without_criteria, m_review_without_trigger, m_logic_mixed_variants,
                m_logic_unknown_kind, m_bad_map_key, m_bad_duration, m_empty_duration, m_bad_datetime,
                m_null_optional, m_extra_property, m_confidence_out_of_range, m_missing_scope, m_wrong_ir_version,
                m_excerpt_too_long]


def _gap_coverage_without_slot():
    g = copy.deepcopy(load(KYC / "gaps_client_kyc.json")[0])
    g["type"] = "coverage_missing"
    g.pop("coverage_slot", None)
    return g


def _patch_on_stories():
    p = load(SAMPLES / "patch_example.json")
    p["ops"] = [{"op": "replace", "path": "/stories/story_x/title", "value": "t"}]
    return p


def _patch_no_ops():
    p = load(SAMPLES / "patch_example.json")
    p["ops"] = []
    return p


def _idea_missing_to_be():
    i = load(KYC / "idea_client_kyc.json")
    del i["to_be_process_id"]
    return i


def _question_text_too_long():
    q = load(SAMPLES / "questions_outbox.json")[0]
    q["text"] = "x" * 401
    return q


def _suggestion_bad_id():
    s = load(KYC / "suggestions_client_kyc.json")[0]
    s["suggestion_id"] = "S1"
    return s


def _session_bad_turn():
    s = load(KYC / "intake_session_kyc.json")
    s["timeline"][0]["turn"] = "turn-0"
    return s


OTHER_INVALID = [
    ("gap", _gap_coverage_without_slot),
    ("patch", _patch_on_stories),
    ("patch", _patch_no_ops),
    ("idea", _idea_missing_to_be),
    ("question", _question_text_too_long),
    ("suggestion", _suggestion_bad_id),
    ("intake-session", _session_bad_turn),
]


def _both_reject(schema_name: str, doc):
    assert validate_schema(doc, schema_name), "schema accepted the mutated document"
    with pytest.raises(ValidationError):
        MODEL_FOR_SCHEMA[schema_name].model_validate(doc)


@pytest.mark.parametrize("mutate", IR_MUTATIONS, ids=lambda f: f.__name__)
def test_ir_core_schema_parity_rejects_invalid_ir(mutate):
    ir = load(KYC / "ir_client_kyc_to_be.json") if mutate in NEEDS_HITL else _ir()
    mutate(ir)
    _both_reject("process-ir", ir)


@pytest.mark.parametrize("schema_name,make", OTHER_INVALID, ids=lambda x: getattr(x, "__name__", x))
def test_ir_core_schema_parity_rejects_invalid_other(schema_name, make):
    _both_reject(schema_name, make())

