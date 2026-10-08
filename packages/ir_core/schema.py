"""JSON Schema validation against schemas/*.json — the normative contract (CLAUDE.md rule 5)."""
import json
import os
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import Issue

SCHEMA_DIR = Path(os.environ.get("RS_SCHEMA_DIR") or Path(__file__).resolve().parents[2] / "schemas")


@cache
def load_schema(name: str) -> dict:
    """`process-ir` → schemas/process-ir.schema.json."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


@cache
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name), format_checker=FormatChecker())


def validate_schema(doc: Any, schema: str = "process-ir") -> list[Issue]:
    """All schema violations, ordered by path. Empty list = valid."""
    found = sorted(_validator(schema).iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
    return [Issue("schema", "".join(f"/{p}" for p in e.absolute_path), e.message) for e in found]
