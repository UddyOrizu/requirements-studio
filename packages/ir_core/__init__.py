"""ir_core — the Process IR contract in code: models, validation, canonical hashing and JSON Patch apply."""
from .canonical import canonical_json, ir_hash
from .errors import Issue, PatchRejected
from .integrity import validate_integrity
from .models import MODEL_FOR_SCHEMA, dump
from .patching import (
    READ_ONLY_PATHS,
    apply_patch,
    changed_paths,
    conflicting_paths,
    forbidden_ops,
    paths_overlap,
)
from .schema import load_schema, validate_schema

__all__ = [
    "MODEL_FOR_SCHEMA", "READ_ONLY_PATHS", "Issue", "PatchRejected", "apply_patch", "canonical_json", "changed_paths",
    "conflicting_paths", "dump", "forbidden_ops", "ir_hash", "load_schema", "paths_overlap", "validate_integrity",
    "validate_schema",
]
