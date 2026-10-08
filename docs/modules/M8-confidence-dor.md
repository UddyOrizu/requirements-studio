# M8 — Confidence & Definition of Ready

## Purpose
Give every element and story an explainable confidence score, and decide deterministically whether each story
is **ready** for MOTHER. Pure functions in `packages/confidence_dor`; no LLM.

## Confidence
Implements IR spec §8 exactly. `score_elements(ir) -> ir` (writes `meta.confidence`), `score_story(ir, story,
gaps) -> float`. Every score is reproducible from the IR + gaps alone.

`explain(element_id)` returns the breakdown for the UI tooltip:
```json
{ "element": "node_screening", "status": "proposed",
  "supports": [{"source": "SOP v4", "w": 0.8, "c": 0.85}, {"source": "Workshop 24 Sep", "w": 0.6, "c": 0.8}],
  "contradicts": [], "evidence": 0.834, "conflict_factor": 1.0, "confidence": 0.834 }
```

## Definition of Ready — checks per story

| ID | Check | Default | Waivable |
|---|---|---|---|
| DOR-01 | Story has an actor that is not `rejected` | required | no |
| DOR-02 | ≥ 1 AC with non-empty Given, When, Then | required | no |
| DOR-03 | Every AC has ≥ 1 observable Then (mentions an entity, actor notification, status, or decision outcome) | required | yes |
| DOR-04 | Every decision in the story has all outcomes wired and a deterministic rule (`table`/`expression`) | required | no |
| DOR-05 | Every wait in the story has a timeout (SLA or timeout exception) | required | no |
| DOR-06 | Every exception in the story has handling ≠ `undefined` | required | yes |
| DOR-07 | Every entity referenced in ACs/rules is defined with the referenced attributes | required | yes |
| DOR-08 | No open **blocking** gaps in the closure | required | no |
| DOR-09 | Story confidence ≥ `ready_threshold` (default 0.80) | required | yes |
| DOR-10 | No ambiguous glossary terms without definition in story ACs | required | yes |
| DOR-12 | Story is linked to ≥ 1 goal (its *so that* expresses business value) | required | no |
| DOR-13 | Priority set (MoSCoW) | required | no |
| DOR-14 | Mandatory NFR categories (`volume`, `security`, `audit` by default) apply to the story | required | yes |
| DOR-15 | If the story contains a decision, wait or exception: ≥ 1 AC of kind `edge_case`/`negative` | required | yes |
| DOR-16 | Every task has a human control (`hitl.mode`). Approval gates have an approver, criteria, and `approved` + `rejected` paths. Reviews have a reviewer | required | no |
| DOR-11 | Process owner sign-off recorded for this story at the current IR version **or** a prior version whose diff doesn't touch the closure | required | no |

Story DoR status: `ready` (all pass), `waived` (only waivable checks fail and each has an owner waiver with reason),
`not_ready`.

Process is `ready` when every non-rejected story is `ready` or `waived`.

Reference implementation: `tools/rs_reference.py::evaluate_dor`. Story rows are byte-identical to the samples.

## Output
`dor_report` (sample: `samples/dor_report.json`): per story → checks with pass/fail and a human message pointing
at the element/gap to fix. Recomputed on `ir.patched`, `gaps.updated`, sign-off and waiver changes.

## Sign-off and waivers
- `POST /stories/{id}/signoff` (owner only) stores `{story_id, ir_version, closure_hash}`. Closure hash = sha256
  of the canonical JSON of the story closure. A later patch that doesn't change the closure hash keeps the sign-off.
- `POST /stories/{id}/waivers {check_id, reason}` (owner only), recorded in audit and exported to MOTHER.

## Acceptance tests
- **AC-M8-1** `score_elements` on the sample IR yields `node_screening.meta.confidence = 0.834` (± 0.001).
- **AC-M8-2** Evaluating the sample IR + sample gaps reproduces `samples/dor_report.json` statuses and failing check ids.
- **AC-M8-3** After applying `patch_example.json` and resolving its gap, `story_high_risk_approval` no longer fails
  DOR-08 but still fails DOR-11 until signed off.
- **AC-M8-5** The client KYC to-be passes all 16 checks for all 9 stories once signed off (`samples/client_kyc/dor_report_kyc.json`).
- **AC-M8-6** The document-led sample fails DOR-12/13/14/16 on every story until goals, priorities, NFRs and human controls are captured.
- **AC-M8-4** A sign-off survives a patch that only touches `node_engagement_letter` for stories whose closure
  excludes it.
