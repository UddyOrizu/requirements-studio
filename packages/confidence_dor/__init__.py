"""M8 confidence and Definition of Ready — pure, deterministic, no LLM. DoR arrives in P3."""
from .confidence import DEFAULT_AUTHORITY_WEIGHTS, explain, score_elements, score_meta

__all__ = ["DEFAULT_AUTHORITY_WEIGHTS", "explain", "score_elements", "score_meta"]
