"""Canonical JSON + sha256 for IR hashing (M3): sorted keys, no whitespace, UTF-8, meta.confidence included."""
import hashlib
import json
from typing import Any

from pydantic import BaseModel

from .models.common import dump


def canonical_json(doc: Any) -> bytes:
    if isinstance(doc, BaseModel):
        doc = dump(doc)
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def ir_hash(doc: Any) -> str:
    return hashlib.sha256(canonical_json(doc)).hexdigest()
