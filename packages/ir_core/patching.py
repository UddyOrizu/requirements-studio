"""RFC 6902 apply for IR patches, with the Patch Service's validation rules (docs/02 §7, M3).

This is the pure part of M3 apply: no locking, versioning, confidence scoring or audit (those are the P1 service).
"""
import copy
from collections.abc import Iterable
from typing import Any

import jsonpatch
import jsonpointer
from pydantic import BaseModel

from .errors import Issue, PatchRejected
from .integrity import validate_integrity
from .models.common import dump
from .schema import validate_schema

# Derived (/stories, rendered by M7) or managed by the Patch Service. No op may touch these, or an ancestor of them.
READ_ONLY_PATHS = ("/stories", "/process/version", "/process/updated_at")


def paths_overlap(a: str, b: str) -> bool:
    """True when one JSON Pointer is the other or an ancestor of it (`/nodes/x` overlaps `/nodes/x/name`)."""
    return a == b or b.startswith(a + "/") or a.startswith(b + "/")


def _touched(op: dict) -> list[str]:
    return [p for p in (op.get("path"), op.get("from")) if isinstance(p, str)]


def changed_paths(ops: Iterable[dict]) -> list[str]:
    """Paths an op list writes (sorted, unique; `test` ops excluded; trailing `/-` dropped). Used for rebase."""
    out: set[str] = set()
    for op in ops:
        if op.get("op") == "test":
            continue
        for p in _touched(op) if op.get("op") == "move" else [op.get("path")]:
            out.add(p.removesuffix("/-"))
    return sorted(out)


def forbidden_ops(ops: Iterable[dict]) -> list[Issue]:
    issues = []
    for i, op in enumerate(ops):
        for p in _touched(op):
            if any(paths_overlap(p, ro) for ro in READ_ONLY_PATHS):
                issues.append(Issue("forbidden_path", f"/ops/{i}",
                                    f"op '{op.get('op')}' touches read-only path {p}"))
    return issues


def apply_patch(ir: dict, patch: dict | BaseModel) -> dict:
    """Apply `patch.ops` to a copy of `ir` and return it, or raise PatchRejected (422) with every issue found.

    Order: forbidden paths → envelope schema → process id → RFC 6902 apply → IR schema → referential integrity.
    The input IR is never modified. `process.version` and `updated_at` are left for the Patch Service to set.
    """
    if isinstance(patch, BaseModel):
        patch = dump(patch)
    ops: list[dict[str, Any]] = patch.get("ops") or []

    if issues := forbidden_ops(ops):
        raise PatchRejected(issues)
    if issues := validate_schema(patch, "patch"):
        raise PatchRejected([Issue("envelope", i.path, i.message) for i in issues])
    if patch["process_id"] != ir["process"]["id"]:
        raise PatchRejected([Issue("envelope", "/process_id",
                                   f"patch is for {patch['process_id']}, IR is {ir['process']['id']}")])

    try:
        doc = jsonpatch.apply_patch(copy.deepcopy(ir), ops)
    except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as e:
        raise PatchRejected([Issue("patch_op", "/ops", str(e))]) from e

    if issues := validate_schema(doc):
        raise PatchRejected(issues)
    if issues := validate_integrity(doc):
        raise PatchRejected(issues)
    return doc
