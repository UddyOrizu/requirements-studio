"""Every sample that has a schema round-trips through the Pydantic models unchanged (CLAUDE.md rule 5)."""
from pathlib import Path

import pytest

from ir_core import canonical_json, dump, validate_schema
from ir_core.models import MODEL_FOR_SCHEMA
from tests.conftest import KYC, SAMPLES, load

# sample file -> (schema name, is the file a list of instances)
SAMPLE_SCHEMAS: dict[Path, tuple[str, bool]] = {
    SAMPLES / "ir_client_onboarding.json": ("process-ir", False),
    SAMPLES / "patch_example.json": ("patch", False),
    SAMPLES / "gaps_client_onboarding.json": ("gap", True),
    SAMPLES / "questions_outbox.json": ("question", True),
    SAMPLES / "ideas_index.json": ("idea", True),
    KYC / "ir_v0_empty.json": ("process-ir", False),
    KYC / "ir_client_kyc_as_is.json": ("process-ir", False),
    KYC / "ir_client_kyc_to_be.json": ("process-ir", False),
    KYC / "idea_client_kyc.json": ("idea", False),
    KYC / "intake_session_kyc.json": ("intake-session", False),
    KYC / "suggestions_client_kyc.json": ("suggestion", True),
    KYC / "gaps_client_kyc.json": ("gap", True),
}

# JSON samples with no schema in schemas/ (fixtures for later phases).
NO_SCHEMA = {
    SAMPLES / "dor_report.json",
    SAMPLES / "sme_directory.json",
    KYC / "dor_report_kyc.json",
}


def _instances():
    for path, (schema, is_list) in SAMPLE_SCHEMAS.items():
        data = load(path)
        items = data if is_list else [data]
        for i, item in enumerate(items):
            label = f"{path.relative_to(SAMPLES)}" + (f"[{i}]" if is_list else "")
            yield pytest.param(schema, item, id=label)
    # Parked intake questions are question.schema.json instances (intake-session.schema.json description).
    for i, q in enumerate(load(KYC / "intake_session_kyc.json")["parked_questions"]):
        yield pytest.param("question", q, id=f"client_kyc/intake_session_kyc.json:parked_questions[{i}]")


def test_ir_core_every_json_sample_is_classified():
    found = set(SAMPLES.rglob("*.json"))
    unclassified = found - set(SAMPLE_SCHEMAS) - NO_SCHEMA
    assert not unclassified, f"add these samples to SAMPLE_SCHEMAS or NO_SCHEMA: {sorted(map(str, unclassified))}"


@pytest.mark.parametrize("schema,instance", list(_instances()))
def test_ir_core_sample_is_schema_valid(schema, instance):
    assert validate_schema(instance, schema) == []


@pytest.mark.parametrize("schema,instance", list(_instances()))
def test_ir_core_sample_roundtrips_unchanged(schema, instance):
    model = MODEL_FOR_SCHEMA[schema].model_validate(instance)
    out = dump(model)
    assert out == instance
    # == treats 1 and 1.0 as equal; the canonical bytes do not.
    assert canonical_json(out) == canonical_json(instance)
