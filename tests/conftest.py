import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
KYC = SAMPLES / "client_kyc"


def load(path: Path):
    return json.loads(path.read_text())


@pytest.fixture
def onboarding_ir() -> dict:
    """Document-led sample IR, version 3 (mid-review, has stories)."""
    return copy.deepcopy(_cached(SAMPLES / "ir_client_onboarding.json"))


@pytest.fixture
def patch_example() -> dict:
    return copy.deepcopy(_cached(SAMPLES / "patch_example.json"))


_cache: dict[Path, object] = {}


def _cached(path: Path):
    if path not in _cache:
        _cache[path] = load(path)
    return _cache[path]
