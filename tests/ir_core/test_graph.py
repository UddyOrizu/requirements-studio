"""ir_core.graph must match the oracle on every sample IR and every replayed intermediate IR (CLAUDE.md rule 7)."""
import pytest

from ir_core import graph
from tests.conftest import KYC, SAMPLES, load
from tests.oracle import R, replayed_irs

SAMPLE_IRS = [load(p) for p in (SAMPLES / "ir_client_onboarding.json", KYC / "ir_client_kyc_as_is.json",
                                KYC / "ir_client_kyc_to_be.json")]
IRS = [pytest.param(ir, id=ir["process"]["id"]) for ir in SAMPLE_IRS] + [
    pytest.param(ir, id=label) for label, ir in replayed_irs()]


@pytest.mark.parametrize("ir", IRS)
def test_ir_core_graph_matches_oracle(ir):
    assert graph.adjacency(ir) == R.adjacency(ir)
    assert graph.bfs_distance(ir) == R.bfs_distance(ir)
    groups = graph.story_groups(ir)
    assert groups == R.story_groups(ir) and list(groups) == list(R.story_groups(ir))
    for ns in groups.values():
        assert graph.closure(ir, ns) == R.closure(ir, ns)
    starts = graph.start_nodes(ir)
    assert graph.reach(graph.adjacency(ir), starts) == R.reach(R.adjacency(ir), starts)
