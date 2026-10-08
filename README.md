# Requirements Studio — Design & Implementation Specification

**Status:** v1.1 build spec (adds idea-first discovery + detailed stories) · **Owner:** Udo · **Consumer:** Claude Code (implementation) and the MOTHER team (downstream)
**Date:** 2026-10-03

Requirements Studio turns the months-long requirements phase into days. **Start from just an idea**: the
discovery interview (M0) asks one well-chosen follow-up question at a time until the idea is a complete process
with detailed, ready user stories. Or start from documents: it ingests what already exists
(SOPs, process docs, emails, meeting transcripts, later screen recordings), drafts the business process as a
diagram, lets people **correct** rather than write, asks targeted questions only where the model is uncertain,
routes each question to the right SME, and produces two synchronised outputs:

**A conversational requirements and discovery tool.** New idea → a conversation about the idea, or about today's process if
one exists → AI suggests where agents can help → **process flow + detailed user stories** → refine → export. Ideas are
listed and each opens to its flow and stories.

**Main outputs** (all rendered from the IR):

| Output | Audience | Format |
|---|---|---|
| **Detailed user stories** with Given/When/Then acceptance criteria | Business, BA, QA, delivery | Markdown + `.feature`; **Jira CSV, Azure DevOps CSV, Excel/CSV** |
| **Process flows** (as-is and to-be) marking automated steps, human-in-the-loop reviews, approval gates and human queues | Process owners, risk, architects | **`.drawio`** (import into Lucidchart as editable shapes) + Mermaid `.mmd` |
| **Improvements report**: AI suggestions, decisions, hours saved | Sponsors, process owners | Markdown + Excel sheet |
| Process IR (machine view, the source of truth) | MOTHER | JSON validated by `schemas/process-ir.schema.json` |

Stories are never edited as prose and parsed back. All change goes through the IR.

---

## How to use this pack (Claude Code)

1. Read `CLAUDE.md` first — it holds the non-negotiable build rules.
2. Read `docs/00-overview.md` → `docs/01-architecture.md` → `docs/02-ir-specification.md`.
3. Build in the order given in `docs/05-implementation-plan.md`. Each phase lists the module specs it needs and
   its exit tests.
4. Use `samples/` as fixtures. Two worked examples:
   - **Client KYC** (`samples/client_kyc/`), the main example: a one-paragraph idea. The requester says a process exists today,
     so the conversation captures the as-is (17 turns). The AI then suggests 7 improvements (6 accepted, 1 rejected, ~275 analyst
     hours a month), and the result is a to-be with 9 ready stories, as-is and to-be flows, one story refinement, and Jira, Azure DevOps,
     Excel and CSV exports. Every patch and decision is in `intake_session_kyc.json`; `conversation_kyc.md` is the readable version.
   - **Document-led** (`samples/*.json`): client onboarding/KYC from an SOP, a transcript and an email, mid-review,
     with conflicts, gaps and stories that aren't ready yet.
5. `tools/rs_reference.py` is the reference implementation (test oracle) of confidence, coverage, next-question
   selection, story derivation and DoR. `python tools/validate_samples.py` replays the idea-first session from an
   empty IR and checks every fixture against the schemas and the oracle.

## File map

```
README.md                       this file
CLAUDE.md                       build rules for Claude Code
docs/
  00-overview.md                what the product is, user journeys, outputs, goals, glossary
  01-architecture.md            module map, data flow, sequences, stack, repo layout, events
  02-ir-specification.md        the Process IR (as-is / to-be), element metadata, patch model, confidence model
  03-api.md                     REST + event contracts
  04-data-model.md              Postgres tables
  05-implementation-plan.md     phased build plan with exit criteria
  06-nfr-security.md            security, confidentiality, audit, performance
  modules/
    M0-idea-intake-discovery.md   ← the conversation (idea mode / as-is mode)
    M11-as-is-improvement.md      ← AI suggests where agents help; accept/reject each
    M12-ideas-workspace-and-refinement.md  ← ideas list, idea detail, story refinement
    M7-story-renderer.md          detailed user stories
    M10-process-flow-diagram.md   Lucidchart-ready flows with HITL + approval gates
    M9-exports.md                 Lucidchart, Markdown, Gherkin, Jira, Azure DevOps, Excel/CSV, MOTHER
    M1-source-ingestion.md        (supporting) document upload
    M2-extraction-reconciliation.md
    M3-ir-store-patch-service.md
    M4-process-canvas-ui.md
    M5-gap-detector.md
    M6-interviewer-sme-routing.md
    M8-confidence-dor.md
schemas/
  process-ir.schema.json        THE contract
  idea.schema.json              an idea (top-level object in the Ideas list)
  suggestion.schema.json        an M11 improvement suggestion
  intake-session.schema.json    the conversation timeline (incl. fork, suggestions, refinements)
  patch.schema.json · gap.schema.json · question.schema.json
prompts/
  README.md                     how prompts are loaded (by file name), file format, gateway rules
  *.md                          one file per prompt, e.g. intake_interpret.md, improve_suggest.md, story_refine.md
samples/
  ideas_index.json              the Ideas list: both sample ideas with stats
  client_kyc/                   ★ main worked example: as-is conversation → AI improvements → to-be → stories → exports
    idea.md                     the only input: one paragraph
    idea_client_kyc.json        the idea record
    intake_session_kyc.json     full timeline: 17 as-is turns, fork, 7 suggestions + decisions, deepen/validate, 1 story refinement
    conversation_kyc.md         the same conversation as a readable transcript
    ir_v0_empty.json            starting IR (as-is)
    ir_client_kyc_as_is.json    today's process (confirmed)
    ir_client_kyc_to_be.json    improved process with stories (status ready)
    suggestions_client_kyc.json 7 suggestions: 6 accepted, 1 rejected, evidence + benefit + ops
    gaps_client_kyc.json · dor_report_kyc.json
    stories_client_kyc.md       9 detailed to-be stories, all ready, with "what changes from today"
    features/client_kyc.feature
    flow/as_is_process_flow.drawio|.mmd   today: all manual, minutes + pain points
    flow/to_be_process_flow.drawio|.mmd   improved: automated steps, human review, 2 approval gates, 3 human queues
    exports/                    jira_import.csv · azure_devops_import.csv · stories_backlog.csv · stories_backlog.xlsx · improvements.md
  (document-led example, supporting path)
  sources/                      raw inputs (SOP, transcript, email thread)
  ir_client_onboarding.json     as-is IR after extraction + first corrections (deliberately has gaps)
  gaps_client_onboarding.json · questions_outbox.json · patch_example.json · dor_report.json · sme_directory.json
  stories_client_onboarding.md · features/client_onboarding.feature
  flow/as_is_process_flow.drawio|.mmd   onboarding flow (controls not yet set, shown dashed)
  export/manifest.yaml          MOTHER package manifest
tools/
  rs_reference.py               reference implementation / test oracle (confidence, coverage, stories, DoR)
  render_flow.py                reference diagram renderer: python tools/render_flow.py <ir.json> <out_dir>
  render_exports.py             reference export renderer: python tools/render_exports.py <to_be.json> <out_dir> [as_is.json suggestions.json]
  validate_samples.py           schema, integrity, replay, suggestion, flow and export checks
```
