"""Shared building blocks for the models that mirror schemas/*.json.

Mirroring rules (checked by tests/ir_core/test_schema_parity.py):
- `additionalProperties: false` → `Closed` (extra="forbid"); an open object → `Open` (extra="allow") or dict[str, Any].
- Required in the schema ⇔ no default here.
- Optional and not nullable → typed without None and defaulted with `absent()`. The default marks the field unset,
  so `dump()` leaves it out, and an explicit null still fails as it does in the schema.
- Nullable (`["string", "null"]`) → `X | None`.
- JSON "number" → `Number` (int | float), so 1 and 1.0 survive a round trip unchanged.
- date-time and ISO 8601 durations stay strings so a round trip never reformats them.
"""
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class Closed(BaseModel):
    # python-re: the Duration and patch-path patterns use lookahead, which the default Rust engine lacks.
    model_config = ConfigDict(extra="forbid", populate_by_name=True, regex_engine="python-re")


class Open(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, regex_engine="python-re")


def absent() -> Any:
    """Default for an optional, non-nullable field: unset, omitted on dump, and null is still rejected."""
    return Field(default=None)


def dump(model: BaseModel) -> Any:
    """Model → JSON-ready value exactly as it would appear in a schema-valid document."""
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def check_date_time(v: str) -> str:
    """RFC 3339 date-time (JSON Schema `format: date-time`), kept as the original string."""
    if "T" not in v.upper():
        raise ValueError("date-time must contain a 'T' separator")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"invalid date-time: {e}") from None
    if dt.tzinfo is None:
        raise ValueError("date-time must carry a UTC offset or 'Z'")
    return v


DateTime = Annotated[str, AfterValidator(check_date_time)]
Duration = Annotated[str, Field(pattern=r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$")]


def Number(ge: float | None = None, le: float | None = None) -> Any:  # noqa: N802 (reads as a type)
    """JSON Schema "number" with optional bounds; keeps ints as ints."""
    return Annotated[int, Field(ge=ge, le=le)] | Annotated[float, Field(ge=ge, le=le)]


Confidence = Number(ge=0, le=1)
NonNegativeNumber = Number(ge=0)
AnyNumber = Number()


def pattern_id(prefix: str) -> Any:
    """String id with a fixed prefix, e.g. pattern_id("node") → ^node_[a-z0-9_]{1,60}$."""
    return Annotated[str, Field(pattern=f"^{prefix}_[a-z0-9_]{{1,60}}$")]


SrcId = pattern_id("src")
ActId = pattern_id("act")
EntId = pattern_id("ent")
NodeId = pattern_id("node")
EdgeId = pattern_id("edge")
RuleId = pattern_id("rule")
ExcId = pattern_id("exc")
SlaId = pattern_id("sla")
AcId = pattern_id("ac")
TermId = pattern_id("term")
StoryId = pattern_id("story")
GoalId = pattern_id("goal")
PersId = pattern_id("pers")
NfrId = pattern_id("nfr")
ProcId = pattern_id("proc")
IdeaId = pattern_id("idea")
ElementId = Annotated[
    str, Field(pattern=r"^(src|act|ent|node|edge|rule|exc|sla|ac|term|story|goal|pers|nfr)_[a-z0-9_]{1,60}$")
]
SuggestionId = Annotated[str, Field(pattern=r"^S[0-9]{2}$")]
JsonPointer = Annotated[str, Field(pattern=r"^/")]


class LooseOp(Open):
    """A JSON Patch op as stored on suggestions and timeline entries: only `op` and `path` are required."""

    op: Any
    path: Any
