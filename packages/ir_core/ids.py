"""IR element id rules (docs/02 §2)."""
import re

PREFIX_TO_COLLECTION = {
    "src": "sources", "act": "actors", "ent": "entities", "node": "nodes", "edge": "edges",
    "rule": "decision_rules", "exc": "exceptions", "sla": "slas", "ac": "acceptance_criteria",
    "term": "glossary", "story": "stories", "goal": "goals", "pers": "personas", "nfr": "nfrs",
}
# Collections whose elements carry `meta` (provenance + confidence).
ELEMENT_COLLECTIONS = ["actors", "entities", "nodes", "edges", "decision_rules", "exceptions", "slas",
                       "acceptance_criteria", "glossary", "goals", "personas", "nfrs"]
# Element statuses that make an element unreferenceable (docs/02 §9: "exists and is not rejected").
DEAD_STATUSES = frozenset({"rejected", "superseded"})
INFERRED_SOURCE_ID = "src_inferred"
ELEMENT_ID_RE = re.compile(r"^(src|act|ent|node|edge|rule|exc|sla|ac|term|story|goal|pers|nfr)_[a-z0-9_]{1,60}$")


def collection_for(element_id: str) -> str | None:
    """`node_screening` → `nodes`; None for an unknown prefix."""
    return PREFIX_TO_COLLECTION.get(element_id.split("_", 1)[0])
