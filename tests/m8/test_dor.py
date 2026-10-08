"""M8 Definition of Ready: oracle parity, the sample reports, sign-off closure hashes."""
import pytest

from confidence_dor import closure_hash, dor_report, evaluate_dor, score_elements
from ir_core import apply_patch
from story_renderer import derive_stories
from tests.conftest import SAMPLES, load
from tests.oracle import R, replayed_irs
from tests.samples import SAMPLES_ALL, kyc, onboarding


def stories_for(sample):
    return derive_stories(sample.base(), sample.gaps, sample.questions, version=sample.ir["process"]["version"])


def test_M8_AC_M8_2():
    """The sample IR + sample gaps reproduce samples/dor_report.json (statuses, failing checks, every field)."""
    sample = onboarding()
    report = dor_report(sample.base(), stories_for(sample), sample.gaps, evaluated_at=sample.dor["evaluated_at"],
                        signoffs=sample.dor["signoffs"])
    assert report == sample.dor


def test_M8_AC_M8_3():
    """After patch_example and resolving its gap, story_high_risk_approval no longer fails DOR-08 but still fails
    DOR-11 until signed off."""
    sample = onboarding()
    ir = score_elements(apply_patch(sample.base(), load(SAMPLES / "patch_example.json")))
    gaps = [{**g, "status": "resolved"} if g["gap_id"] == "gap_high_risk_approver_conflict" else g
            for g in sample.gaps]

    def failed(signoffs=()):
        stories = derive_stories(ir, gaps)
        row = next(r for r in evaluate_dor(ir, stories, gaps, signoffs=set(signoffs))
                   if r["story_id"] == "story_high_risk_approval")
        return row["failed_checks"]

    assert "DOR-08" not in failed() and "DOR-11" in failed()
    assert "DOR-11" not in failed(signoffs=["story_high_risk_approval"])


def test_M8_AC_M8_4():
    """A sign-off survives a patch that only touches node_engagement_letter, for stories whose closure excludes it."""
    ir = onboarding().base()
    stories = derive_stories(ir, [])
    before = {sid: closure_hash(ir, s) for sid, s in stories.items()}
    rename = {"op": "replace", "path": "/nodes/node_engagement_letter/name", "value": "Send engagement letter"}
    patch = {"patch_id": "p", "process_id": ir["process"]["id"], "base_version": 3, "ops": [rename],
             "author": {"kind": "user", "id": "u"}, "reason": "rename", "auto_apply": True, "status": "proposed"}
    after_ir = apply_patch(ir, patch)
    after = {sid: closure_hash(after_ir, s) for sid, s in derive_stories(after_ir, []).items()}
    changed = {sid for sid in before if before[sid] != after[sid]}
    assert changed == {"story_engagement_letter"}


def test_M8_AC_M8_5():
    """The client KYC to-be passes all 16 checks for all 9 stories once signed off."""
    sample = kyc()
    stories = stories_for(sample)
    rows = evaluate_dor(sample.base(), stories, sample.gaps, signoffs=set(stories))
    assert len(rows) == 9 and all(r["status"] == "ready" and r["failed_checks"] == [] for r in rows)
    assert all(len(r["checks"]) == 16 for r in rows)
    report = dor_report(sample.base(), stories, sample.gaps, evaluated_at=sample.dor["evaluated_at"],
                        signoffs=sample.dor["signoffs"])
    assert report == sample.dor


def test_M8_AC_M8_6():
    """The document-led sample fails DOR-12/13/14/16 on every story."""
    sample = onboarding()
    for row in evaluate_dor(sample.base(), stories_for(sample), sample.gaps):
        assert {"DOR-12", "DOR-13", "DOR-14", "DOR-16"} <= set(row["failed_checks"]), row["story_id"]


def test_m8_waivers_only_cover_waivable_checks():
    sample = kyc()
    ir = sample.base()
    stories = stories_for(sample)
    sid = "story_screen"
    waivers = [{"story_id": sid, "check_id": "DOR-09"}]
    stories[sid]["confidence"] = 0.5  # fails DOR-09 (waivable)
    [row] = [r for r in evaluate_dor(ir, stories, [], signoffs=set(stories), waivers=waivers) if r["story_id"] == sid]
    assert row["status"] == "waived"
    ir["nodes"]["node_screen"].pop("hitl")  # DOR-16 is not waivable
    [row] = [r for r in evaluate_dor(ir, stories, [], signoffs=set(stories),
                                     waivers=waivers + [{"story_id": sid, "check_id": "DOR-16"}])
             if r["story_id"] == sid]
    assert row["status"] == "not_ready"


@pytest.mark.parametrize("label,ir", [(k, v) for k, v in replayed_irs()
                                      if all(n.get("actor_id") for n in v["nodes"].values() if n["type"] == "task")])
def test_m8_evaluate_dor_matches_oracle_on_replay(label, ir):
    gaps = load(SAMPLES / "client_kyc" / "gaps_client_kyc.json")
    ours = derive_stories(ir, gaps)
    theirs = R.derive_stories(ir, gaps)
    signoffs = set(list(ours)[::2])
    assert evaluate_dor(ir, ours, gaps, signoffs=signoffs) == R.evaluate_dor(ir, theirs, gaps, signoffs=signoffs)
    assert ours == theirs  # evaluate_dor sets dor_status in place on both


@pytest.mark.parametrize("make", SAMPLES_ALL, ids=lambda f: f.__name__)
def test_m8_stored_stories_carry_the_evaluated_status(make):
    sample = make()
    stories = stories_for(sample)
    evaluate_dor(sample.base(), stories, sample.gaps, signoffs=set(sample.dor["signoffs"]))
    assert stories == sample.ir["stories"]
