"""The test oracle (tools/rs_reference.py) and the KYC timeline replay, shared by parity tests."""
import copy
import importlib.util
import sys

import jsonpatch

from tests.conftest import KYC, ROOT, load


def _load(name: str):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


R = _load("rs_reference")


def replayed_irs():
    """(label, IR) after every KYC timeline patch, as tools/validate_samples.py replays it (as-is, fork, to-be),
    with confidence re-scored and process.version set the way the Patch Service stores each version.

    Labels carry the process variant and version, e.g. "as_is@v5", "to_be@v0".
    """
    session = load(KYC / "intake_session_kyc.json")
    irs = {"as_is": load(KYC / "ir_v0_empty.json"), "to_be": None}
    version = {"as_is": 0, "to_be": 0}
    for e in session["timeline"]:
        v = e.get("process", "as_is")
        if e["kind"] == "fork":
            irs["to_be"] = copy.deepcopy(irs["as_is"])
            irs["to_be"]["process"].update(e["fork"]["process_overrides"])
            yield "to_be@v0", copy.deepcopy(irs["to_be"])
        elif e.get("ops"):
            irs[v] = jsonpatch.apply_patch(irs[v], e["ops"])
            version[v] = e["ir_version_after"]
            irs[v]["process"]["version"] = version[v]
            R.score_all(irs[v])
            yield f"{v}@v{version[v]}", copy.deepcopy(irs[v])
