"""End-to-end test 1 (docs/05): one-paragraph idea → improved process, stories, flows and exports.

The whole client KYC session through M0 + M11 with recorded LLM responses (tests/cassettes). Stand-ins remain for
M12 story refinement (the recorded patch), the M6 SME answer (the recorded interviewer patch) and the M5 semantic
detector (gap_match_threshold seeded). Exports use the reference renderer (tools/render_exports.py) until M9 (P7).
"""
import csv
import io
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from confidence_dor import evaluate_dor
from exporters import improvements_md
from flow_renderer import render_drawio, render_mermaid
from ir_core.ids import ELEMENT_COLLECTIONS
from services.gaps.store import stored_gaps
from services.improve.service import ImproveService
from services.intake.service import IntakeService
from services.interviewer.db import Question
from story_renderer import derive_stories, render_gherkin, render_markdown
from tests.conftest import KYC, load
from tests.m0 import kyc_replay as K
from tests.m0.test_intake import gateway
from tests.oracle import _load
from tests.samples import kyc

RX = _load("render_exports")
RECORD = os.environ.get("RS_RECORD_CASSETTES") == "1"


def _strip(ir: dict) -> dict:
    """Excluding confidence (the scenario says so), stories, and the process header's clock fields."""
    out = {c: {k: {**v, "meta": {m: x for m, x in v["meta"].items() if m != "confidence"}}
               for k, v in ir[c].items()} for c in ELEMENT_COLLECTIONS}
    return {**out, "scope": ir["scope"], "sources": {k: {f: x for f, x in v.items() if f != "ingested_at"}
                                                     for k, v in ir["sources"].items()}}


@pytest.fixture
async def finished(tx_sessionmaker):
    async with tx_sessionmaker() as db:
        await K.seed_smes(db)
        svc = IntakeService(db, gateway("record" if RECORD else "replay"), clock=K.Clock(), correlation_id="e2e")
        replay = await K.start(svc)
        await K.to_the_end(replay)
        yield svc, replay


async def test_end_to_end_1_client_kyc(finished):
    svc, replay = finished
    db = svc.s

    # Discover: every question targets the slot recorded in the session, in the same order.
    discover = [(label, target) for label, target in replay.asked if K.TURNS[label]["phase"] == "discover"]
    assert [t for _, t in discover] == [K.TURNS[label]["target"] for label, _ in discover]

    # The as-is equals the stored file (excluding confidence).
    as_is = await svc.patches.get_ir("proc_client_kyc_as_is")
    assert _strip(as_is) == _strip(load(KYC / "ir_client_kyc_as_is.json"))

    # Suggestions match in target, kind and benefit; S01–S06 accepted, S07 rejected with its reason.
    improve = ImproveService(db, svc.llm, clock=svc.clock)
    suggestions = await improve.list_suggestions("idea_client_kyc")
    want = load(KYC / "suggestions_client_kyc.json")
    assert [(s["target_refs"], s["kind"], s["benefit"], s["status"]) for s in suggestions] == \
        [(s["target_refs"], s["kind"], s["benefit"], s["status"]) for s in want]
    assert suggestions[6]["decision"]["reason"] == want[6]["decision"]["reason"]

    # The to-be equals the stored file (excluding confidence). One documented difference: M0 §2 asks Deepen gaps by
    # priority, so the SLA answer is turn T19 here (the recorded session asked it first, as T18).
    to_be = await svc.patches.get_ir("proc_client_kyc_to_be")
    stored = load(KYC / "ir_client_kyc_to_be.json")
    [ref] = [p for p in stored["slas"]["sla_kyc_checks"]["meta"]["provenance"]
             if p["locator"] == {"kind": "turn", "value": "T18"}]
    ref["locator"]["value"] = "T19"
    assert _strip(to_be) == _strip(stored)
    assert to_be["process"]["version"] == stored["process"]["version"] == 12

    # All 9 stories are ready and match the stories file and the feature file.
    gaps = [g.as_gap() for g in await stored_gaps(db, "proc_client_kyc_to_be")]
    questions = [{"gap_ids": q.gap_ids, "sme_id": q.sme_id, "status": q.status}
                 for q in (await db.execute(select(Question))).scalars()]
    to_be["stories"] = derive_stories(to_be, gaps, questions, version=to_be["process"]["version"])
    rows = evaluate_dor(to_be, to_be["stories"], gaps, signoffs=set(to_be["stories"]))
    assert len(rows) == 9 and all(r["status"] == "ready" for r in rows)
    sample = kyc()
    assert render_markdown(to_be, rows, as_is=as_is, origin=sample.origin) == \
        (KYC / "stories_client_kyc.md").read_text()
    assert render_gherkin(to_be, description=sample.feature_description) == \
        (KYC / "features" / "client_kyc.feature").read_text()

    # Both flows match.
    for variant, ir in (("as_is", as_is), ("to_be", to_be)):
        assert render_drawio(ir) == (KYC / "flow" / f"{variant}_process_flow.drawio").read_text()
        assert render_mermaid(ir) == (KYC / "flow" / f"{variant}_process_flow.mmd").read_text()

    # The exports match.
    title, desc = "Client KYC checks", to_be["process"]["description"]
    exports = KYC / "exports"
    assert RX.jira_csv(to_be, to_be["stories"], title, desc) == (exports / "jira_import.csv").read_text()
    assert RX.ado_csv(to_be, to_be["stories"], title, desc) == (exports / "azure_devops_import.csv").read_text()
    assert RX.backlog_csv(to_be, to_be["stories"]) == (exports / "stories_backlog.csv").read_text()
    assert improvements_md(as_is, to_be, suggestions) == (exports / "improvements.md").read_text()
    with tempfile.TemporaryDirectory() as tmp:
        RX.backlog_xlsx(Path(tmp) / "backlog.xlsx", to_be, to_be["stories"], as_is, suggestions)
        from openpyxl import load_workbook
        got, wanted = load_workbook(Path(tmp) / "backlog.xlsx"), load_workbook(exports / "stories_backlog.xlsx")
        for name in RX.SHEETS:
            assert [list(r) for r in got[name].iter_rows(values_only=True)] == \
                [list(r) for r in wanted[name].iter_rows(values_only=True)], name
    assert list(csv.reader(io.StringIO((exports / "jira_import.csv").read_text())))[1][1] == "Epic"
