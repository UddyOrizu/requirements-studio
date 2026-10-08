"""M5 deterministic gap detection (§A structural, §B conflict, §E story readiness), priority and fingerprints.

Pure functions of the IR; no LLM. The M5 service (services/gaps) persists gaps and runs the semantic detector.
"""
from .detect import DETERMINISTIC_DETECTORS, Reconciliation, detect_gaps, reconcile
from .findings import Finding, fingerprint
from .priority import PriorityModel

__all__ = ["DETERMINISTIC_DETECTORS", "Finding", "PriorityModel", "Reconciliation", "detect_gaps", "fingerprint",
           "reconcile"]
