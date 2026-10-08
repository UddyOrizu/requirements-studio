# 05 — Implementation Plan

Build in phases. Each phase ends with its exit tests green and a demo on the client KYC sample.
The ordering front-loads the deterministic core so every LLM-backed module has something solid to write to.

| Phase | Scope | Module specs | Exit criteria |
|---|---|---|---|
| **P0 Foundations** | Repo scaffold, CI, Docker Compose (Postgres+pgvector, Redis, MinIO), `ir_core` (Pydantic models mirroring every schema, `validate_schema`, `validate_integrity`, canonical JSON + hash, JSON Patch apply), dev OIDC stub, audit log, event outbox | 02, 04, M3 | Pydantic⇄JSON Schema parity test on all samples; `tools/validate_samples.py` in CI; AC-M3-2/4/5 |
| **P1 Patch service + confidence** | M3 apply/rebase/review incl. multiple processes per idea, `confidence_dor.score_elements` | M3, M8 (confidence) | AC-M3-1/3, AC-M8-1 |
| **P2 LLM gateway + structural gaps** | S1 gateway loading prompts by file name (validated at startup), RecordReplay cassettes; `gap_rules` structural + story checks (pure Python) | S1, M5 §A, §E | gateway tests; structural gaps on both samples |
| **P3 Stories, flows + DoR** | M7 detailed renderer + Gherkin; M10 flows (as-is + to-be annotations); M8 DoR incl. DOR-12..16, sign-off, waivers. Port `rs_reference.py` and `render_flow.py` | M7, M8, M10 | AC-M7-1..5, AC-M8-2..6, AC-M10-1..5 (byte-identical to samples) |
| **P4 Conversation (M0)** | Ideas + intake session state machine, **idea mode and as-is mode**, coverage incl. C17, `next_target`, turn loop with `prompts/intake_*.md`, captured cards + undo, ask-someone parking (email/portal), playback, AC drafting, Deepen/Validate on the to-be; conversation UI with live flow | M0 | AC-M0-1..8 |
| **P5 AI improvement (M11)** | Fork, heuristics, `prompts/improve_suggest.md`, guardrails, benefit maths, suggestion cards with accept/reject/edit, improvements report | M11 | AC-M11-1..5; **end-to-end test 1** |
| **P6 Ideas workspace + refinement (M12)** | Ideas list, New idea, Idea detail tabs (Overview, Conversation, Flow with as-is/to-be/compare, Improvements, Stories, Export), story detail with refine chat (`prompts/story_refine.md`), split/merge, history/undo | M12, M4 (read + compare) | AC-M12-1..5 (Playwright for UI) |
| **P7 Exports (M9)** | Lucidchart/Mermaid, Markdown, Gherkin, Jira CSV, Azure DevOps CSV, Excel/CSV backlog, export screen + history. Port `render_exports.py` | M9 | AC-M9-1..3, AC-M9-5 |
| **P8 Supporting: documents, gaps inbox, canvas editing** | M1 ingestion, M2 extraction/reconciliation, semantic + coverage gaps (M5), gap inbox, full canvas editing (M4) | M1, M2, M4, M5 | AC-M1/M2/M4/M5; end-to-end test 2 up to DoR |
| **P9 Supporting: SME routing + MOTHER** | M6 routing, batching, Teams adapter, reminders; MOTHER package + webhook | M6, M9 (MOTHER) | AC-M6-1..5, AC-M9-4; end-to-end test 2 |
| **P10 Extensions** | Spreadsheets, screen recordings, SharePoint/Teams connectors, PII redaction, cycle-time analytics | M1 | per feature |

> The core journeys (new idea → conversation → improve → flow + stories → refine → export) are complete at **P7**.
> P8–P10 add the supporting capabilities you asked to keep.

## End-to-end test 1 — conversation with as-is improvement (must pass at P5; UI version at P7)

```gherkin
Feature: One-paragraph idea to improved process, stories and exports
  Scenario: Simple client KYC
    Given a new idea with the text in samples/client_kyc/idea.md
    And the requester answers "yes" to "Is there a process today?"
    When the requester gives each answer in samples/client_kyc/intake_session_kyc.json in order
    And James Patel answers q_intake_01 with the sample answer
    Then every Discover question targets the slot recorded in the session
    And the as-is equals samples/client_kyc/ir_client_kyc_as_is.json (excluding confidence)
    When the as-is is confirmed and suggestions are generated
    Then the suggestions match samples/client_kyc/suggestions_client_kyc.json in target, kind and benefit
    When S01–S06 are accepted and S07 is rejected with its reason
    And the Deepen and Validate answers and the story refinement are given
    Then the to-be equals samples/client_kyc/ir_client_kyc_to_be.json (excluding confidence)
    And all 9 stories are ready and match samples/client_kyc/stories_client_kyc.md
    And both flows match samples/client_kyc/flow/*_process_flow.drawio
    And the exports match samples/client_kyc/exports/*
```
Use recorded LLM responses (cassettes) for the intake, improvement and refinement prompts so the replay is deterministic.
The expected patches are the `ops` in the session timeline. Suggestions are compared on target, kind and benefit, not wording.

## End-to-end test 2 — document-led (must pass at P8)

```gherkin
Feature: Sources to MOTHER package
  Scenario: Client onboarding
    Given a new process "Client onboarding – KYC & engagement acceptance"
    And the three files in samples/sources are uploaded
    When extraction completes
    Then the gap inbox contains every structural and conflict gap in samples/gaps_client_onboarding.json
    When each routed question in samples/questions_outbox.json is answered with its sample answer
    And the process owner accepts the resulting patches and signs off every story
    Then the DoR dashboard shows all stories ready
    When the owner exports the process
    Then a package is produced whose ir.json validates against schemas/process-ir.schema.json
    And MOTHER's mock webhook receives the export with a matching ir_hash
```

LLM determinism in tests: S1 has a `RecordReplay` mode keyed by `(prompt_file, prompt_sha256, sha256(variables))`, so editing a prompt file invalidates its cassettes. Record once
against a real model, commit cassettes under `tests/cassettes/`, replay in CI.

## Suggested work breakdown for Claude Code sessions

1. "Implement P0 per CLAUDE.md and docs/05 — start with packages/ir_core and its tests. Use tools/rs_reference.py
   as the oracle for confidence, coverage, stories and DoR."
2. One session per phase thereafter, always pointing at the phase row and its module spec(s).
3. After each phase: run full test suite + `tools/validate_samples.py`; update `CHANGELOG.md`.

## Open decisions (owner: Udo)

| # | Decision | Default assumed in this spec |
|---|---|---|
| D1 | Hosting (Azure tenant, AKS vs App Service) | Containers; Azure Blob; Entra ID |
| D2 | Prompt storage | Files in `prompts/`, versioned by git (decided) |
| D10 | Default backlog export | Jira or Azure DevOps per tenant setting; both always available |
| D11 | Azure DevOps process template | Agile (Feature → User Story); `RS_ADO_PROCESS=scrum` for PBIs |
| D3 | Teams integration approval at BDO | Email + portal first; Teams adapter behind a flag |
| D4 | Auto-accept policy on by default? | Off |
| D5 | MOTHER import contract | Webhook + package URI; MOTHER pulls |
| D6 | Model choices per prompt | `RS_LLM_MODEL` default; optional `model:` in a prompt file's front matter |
| D7 | Coverage checklist order/weights per tenant | Default table in M0 §1 |
| D8 | Voice input in v1? | Yes, ASR through S1; audio not stored |
| D9 | Mandatory NFR categories for DoR | volume, security, audit |
