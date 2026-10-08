"""M10 process flow: byte-identical to the reference renderer and the samples; structure and KYC specifics."""
import xml.etree.ElementTree as ET

import pytest

from flow_renderer import STYLE, control, hitl_summary, render_drawio, render_mermaid
from ir_core.graph import live
from tests.conftest import KYC, SAMPLES, load
from tests.oracle import _load, replayed_irs

RF = _load("render_flow")
FLOWS = [(SAMPLES / "ir_client_onboarding.json", SAMPLES / "flow" / "as_is_process_flow"),
         (KYC / "ir_client_kyc_as_is.json", KYC / "flow" / "as_is_process_flow"),
         (KYC / "ir_client_kyc_to_be.json", KYC / "flow" / "to_be_process_flow")]


@pytest.mark.parametrize("ir_path,flow", FLOWS, ids=lambda x: x.name)
def test_M10_AC_M10_1(ir_path, flow):
    """Rendering the sample IRs reproduces the sample .drawio and .mmd files byte for byte."""
    ir = load(ir_path)
    assert render_drawio(ir) == flow.with_suffix(".drawio").read_text()
    assert render_mermaid(ir) == flow.with_suffix(".mmd").read_text()


@pytest.mark.parametrize("label,ir", list(replayed_irs()))
def test_m10_matches_reference_renderer_on_replay(label, ir):
    assert render_drawio(ir) == RF.render_drawio(ir)
    assert render_mermaid(ir) == RF.render_mermaid(ir)
    assert hitl_summary(ir) == RF.hitl_summary(ir)


@pytest.mark.parametrize("ir_path,flow", FLOWS, ids=lambda x: x.name)
def test_M10_AC_M10_2(ir_path, flow):
    """The draw.io file parses; every live node is a cell styled for its control; every edge's ends exist."""
    ir = load(ir_path)
    root = ET.fromstring(render_drawio(ir).encode())
    cells = {c.get("id"): c for c in root.iter("mxCell")}
    for nid in live(ir, "nodes"):
        assert cells[nid].get("style") == STYLE.get(control(ir, nid), STYLE["automated"]), nid
    for c in cells.values():
        if c.get("edge") == "1":
            assert c.get("source") in cells and c.get("target") in cells, c.get("id")


def _cells(ir):
    root = ET.fromstring(render_drawio(ir).encode())
    return {c.get("id"): c for c in root.iter("mxCell")}


def _lane_of(cells, cid):
    """The lane (by header text) whose vertical band contains the cell."""
    y = float(cells[cid].find("mxGeometry").get("y"))
    for lid, c in cells.items():
        if lid.startswith("lanehead_"):
            g = c.find("mxGeometry")
            if float(g.get("y")) <= y < float(g.get("y")) + float(g.get("height")):
                return c.get("value")
    return None


def _edge(cells, src, tgt):
    return next(c for c in cells.values() if c.get("edge") == "1" and c.get("source") == src
                and c.get("target") == tgt)


def test_M10_AC_M10_3():
    ir = load(KYC / "ir_client_kyc_to_be.json")
    cells = _cells(ir)
    for nid, n in ir["nodes"].items():
        if n.get("change"):
            assert f"Changed by {n['change']['suggestion_id']}" in cells[nid].get("value"), nid

    review = cells["node_analyst_review"]
    assert "shape=hexagon" in review.get("style") and _lane_of(cells, "node_analyst_review") == "Onboarding Analyst"
    assert _edge(cells, "node_analyst_review", "node_record_kyc").get("value") == "Approved"
    escalate = _edge(cells, "node_analyst_review", "node_mlro_approval")
    assert escalate.get("value") == "Rejected: escalate to MLRO" and escalate.get("style") == STYLE["edge_reject"]

    assert "shape=hexagon" in cells["node_mlro_approval"].get("style")
    assert _lane_of(cells, "node_mlro_approval") == "MLRO"
    decline = _edge(cells, "node_mlro_approval", "node_decline")
    assert decline.get("value") == "Rejected" and decline.get("style") == STYLE["edge_reject"]
    assert _lane_of(cells, "node_decline") == "Engagement Manager"

    screen = cells["node_screen"]
    assert screen.get("style") == STYLE["hitl_review"]
    assert "Reviewed by Onboarding Analyst (on exceptions)" in screen.get("value")

    queues = {c.get("value"): cid for cid, c in cells.items() if cid.startswith("queue_")}
    id_failed = next(cid for v, cid in queues.items() if "ID check failed" in v)
    no_docs = next(cid for v, cid in queues.items() if "No documents after 10 working days" in v)
    assert _lane_of(cells, id_failed) == "Onboarding Analyst"
    assert _lane_of(cells, no_docs) == "Engagement Manager"


def test_m10_hitl_summary_lists_every_human_touchpoint():
    rows = hitl_summary(load(KYC / "ir_client_kyc_to_be.json"))
    assert [r["control"] for r in rows] == ["human_queue", "human_queue", "hitl_review", "approval", "approval",
                                            "human_queue", "human_task"]
