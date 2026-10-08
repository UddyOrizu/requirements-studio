"""M7: story derivation (oracle parity), Markdown and Gherkin (byte-identical to the samples)."""
import copy

import pytest
from gherkin.parser import Parser

from confidence_dor import evaluate_dor
from story_renderer import derive_stories, render_gherkin, render_markdown
from tests.conftest import SAMPLES
from tests.oracle import R, replayed_irs
from tests.samples import SAMPLES_ALL, kyc


def render(sample, **kw):
    ir = sample.base()
    ir["stories"] = derive_stories(ir, sample.gaps, sample.questions, version=ir["process"]["version"])
    rows = evaluate_dor(ir, ir["stories"], sample.gaps, signoffs=set(sample.dor["signoffs"]))
    return ir, rows, render_markdown(ir, rows, as_is=sample.as_is, origin=sample.origin, **kw)


@pytest.mark.parametrize("make", SAMPLES_ALL, ids=lambda f: f.__name__)
def test_M7_AC_M7_1(make):
    """derive_stories equals the stored stories exactly, and the markdown matches the sample file."""
    sample = make()
    ir, _, markdown = render(sample)
    assert ir["stories"] == sample.ir["stories"]  # including dor_status, set by evaluate_dor
    assert markdown == (SAMPLES / sample.markdown_file).read_text()


def test_M7_AC_M7_2():
    """node_risk_decision folds into story_risk_rate; node_wait_docs folds into story_request_docs."""
    from tests.samples import onboarding
    stories = derive_stories(onboarding().base(), [])
    assert "node_risk_decision" in stories["story_risk_rate"]["node_ids"]
    assert "node_wait_docs" in stories["story_request_docs"]["node_ids"]
    assert not any(sid in stories for sid in ("story_risk_decision", "story_wait_docs"))


@pytest.mark.parametrize("make", SAMPLES_ALL, ids=lambda f: f.__name__)
def test_M7_AC_M7_3(make):
    """Gherkin parses with gherkin-official, has one scenario per AC, and matches the sample file."""
    sample = make()
    feature = render_gherkin(sample.ir, description=sample.feature_description)
    assert feature == (SAMPLES / sample.feature_file).read_text()
    doc = Parser().parse(feature)
    scenarios = [c["scenario"] for c in doc["feature"]["children"]]
    acs = {a for s in sample.ir["stories"].values() for a in s["ac_ids"]}
    assert len(scenarios) == len(acs)
    assert {t["name"][1:] for sc in scenarios for t in sc["tags"] if t["name"][1:].startswith("ac_")} == acs


def test_m7_gherkin_lists_a_shared_ac_once_with_every_story():
    ir = copy.deepcopy(kyc().ir)
    ir["stories"]["story_verify_id"]["ac_ids"].append("ac_request_docs")
    feature = render_gherkin(ir)
    assert feature.count("Scenario: Document request sent through the portal") == 1
    assert "@story_request_docs @story_verify_id @ac_request_docs" in feature


@pytest.mark.parametrize("make", SAMPLES_ALL, ids=lambda f: f.__name__)
def test_M7_AC_M7_4(make):
    """Re-rendering an unchanged IR yields byte-identical markdown (polish off)."""
    sample = make()
    assert render(sample)[2] == render(sample)[2]
    ir, rows, first = render(sample)
    assert render_markdown(copy.deepcopy(ir), rows, as_is=sample.as_is, origin=sample.origin) == first


def test_M7_AC_M7_5():
    """Every KYC to-be story's so_that contains its outcome and a goal statement; story_screen lists
    gap_match_threshold as an open question waiting on sme_priya_shah."""
    sample = kyc()
    stories = derive_stories(sample.base(), sample.gaps, sample.questions)
    ir = sample.ir
    for s in stories.values():
        node = ir["nodes"][s["node_ids"][0]]
        assert node["outcome"] in s["so_that"]
        assert any(ir["goals"][g]["statement"][1:] in s["so_that"] for g in s["goal_ids"])
    [q] = stories["story_screen"]["open_questions"]
    assert (q["gap_id"], q["asked_to"]) == ("gap_match_threshold", "sme_priya_shah")


@pytest.mark.parametrize("label,ir", [(k, v) for k, v in replayed_irs()
                                      if all(n.get("actor_id") for n in v["nodes"].values() if n["type"] == "task")])
def test_m7_derive_stories_matches_oracle_on_replay(label, ir):
    assert derive_stories(ir, [], version=1) == R.derive_stories(ir, [], version=1)


def test_m7_tasks_without_an_actor_block_derivation_clearly():
    from tests.samples import onboarding
    ir = onboarding().base()
    ir["nodes"]["node_screening"].pop("actor_id")
    with pytest.raises(ValueError, match="node_screening"):
        derive_stories(ir, [])
