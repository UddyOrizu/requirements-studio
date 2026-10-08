# 02 — Process IR Specification

The Process IR is the contract between Requirements Studio and MOTHER. Normative definition:
`schemas/process-ir.schema.json` (JSON Schema 2020-12, **IR v1.1**). This document explains intent and rules.
Reference implementation of every formula below: `tools/rs_reference.py` (test oracle).

## 1. Top-level shape

```jsonc
{
  "ir_version": "1.1",
  "process": { "id", "name", "description", "domain", "owner_user_id", "status", "version", "updated_at" },
  "sources":            { "<src_id>":   Source },
  "actors":             { "<act_id>":   Actor },
  "entities":           { "<ent_id>":   Entity },
  "nodes":              { "<node_id>":  Node },
  "edges":              { "<edge_id>":  Edge },
  "decision_rules":     { "<rule_id>":  DecisionRule },
  "exceptions":         { "<exc_id>":   ExceptionCase },
  "slas":               { "<sla_id>":   SLA },
  "acceptance_criteria":{ "<ac_id>":    AcceptanceCriterion },
  "glossary":           { "<term_id>":  GlossaryTerm },
  "goals":              { "<goal_id>":  Goal },        // v1.1 — why the process exists, with metrics
  "personas":           { "<pers_id>":  Persona },     // v1.1 — who benefits
  "nfrs":               { "<nfr_id>":   NFR },         // v1.1 — volume, security, audit, compliance…
  "scope":              Scope,                         // v1.1 — in / out / assumptions / constraints / confirmed_none
  "stories":            { "<story_id>": Story }     // DERIVED by M7; never patched by humans
}
```

Collections are **maps keyed by id** so JSON Patch paths are stable.

## 2. ID prefixes

| Prefix | Element | Example |
|---|---|---|
| `src_` | Source | `src_sop_onboarding_v4` |
| `act_` | Actor | `act_mlro` |
| `ent_` | Entity | `ent_kyc_document_set` |
| `node_` | Node | `node_wait_docs` |
| `edge_` | Edge | `edge_risk_high` |
| `rule_` | Decision rule | `rule_risk_rating` |
| `exc_` | Exception | `exc_id_expired` |
| `sla_` | SLA | `sla_onboarding_total` |
| `ac_` | Acceptance criterion | `ac_screening_complete` |
| `term_` | Glossary term | `term_promptly` |
| `story_` | Story | `story_screen_client` |
| `goal_` | Goal | `goal_faster_kyc` |
| `pers_` | Persona | `pers_audit_senior` |
| `nfr_` | Non-functional requirement | `nfr_portal_only` |

Pattern: `^(src|act|ent|node|edge|rule|exc|sla|ac|term|story|goal|pers|nfr)_[a-z0-9_]{1,60}$`. IDs are immutable; renaming
changes `name`, never the id.

## 3. Element metadata (`meta`)

Every element except `process`, `sources` and `stories` carries:

```json
"meta": {
  "status": "proposed | confirmed | rejected | superseded",
  "confidence": 0.0,
  "provenance": [ProvenanceRef],
  "confirmed_by": "user id or sme id (when status=confirmed)",
  "notes": "free text"
}
```

`ProvenanceRef`:

```json
{
  "source_id": "src_sop_onboarding_v4",
  "locator": { "kind": "page|line_range|timestamp|paragraph|cell|message", "value": "p3 §4.2" },
  "excerpt": "≤ 300 chars, verbatim from the source",
  "stance": "supports | contradicts",
  "extraction_certainty": 0.0
}
```

`src_inferred` is a reserved source id for elements the model inferred with no direct evidence
(e.g. an implied end node). Its authority weight is 0.3.

`rejected` elements stay in the IR (with history) but are ignored by gap checks, rendering and export.

## 4. Node types (BPMN-lite)

| Type | Meaning | Required | Typical gaps |
|---|---|---|---|
| `start` | Process trigger | exactly one outgoing edge | — |
| `end` | Terminal outcome | no outgoing edges | — |
| `task` | Unit of work by one actor | `actor_id` | no actor, no AC |
| `decision` | Exclusive branch | ≥ 2 outgoing edges, each with `condition.outcome` | missing branch, no default |
| `wait` | Waiting on an external party / timer | `sla_ids` or timeout exception | wait without timeout |
| `event` | Intermediate signal (e.g. "document received") | — | — |
| `subprocess` | Reference to another process IR | `subprocess_ref` | — |

Task fields added in v1.1 (all feed the detailed story, M7):

| Field | Meaning |
|---|---|
| `outcome` | What the step achieves for the business. Becomes the first half of the story's *so that*. |
| `goal_ids` | Goals the step serves. Becomes the second half of *so that*, plus the story's beneficiaries and metrics. |
| `system_ids` | System actors the step uses (the performer stays in `actor_id`). Becomes story dependencies and MOTHER tool hints. |
| `priority` | MoSCoW (`must`/`should`/`could`/`wont`), set in Validate. |

### Human-in-the-loop (`hitl`, v1.1) — every task must have one (DOR-16)

| `hitl.mode` | Meaning | Required | Drawn as (M10) |
|---|---|---|---|
| `automated` | No person involved | — | blue `[AUTO]` |
| `hitl_review` | AI/system does it; a named person reviews before it takes effect | `actor_id` (reviewer), `trigger` | amber `[AUTO + HUMAN REVIEW]` |
| `human_task` | A person does it | — (performer = `actor_id` on the node) | white `[HUMAN]` |
| `approval` | **Approval gate**: a named approver approves or rejects before the flow continues | `actor_id` (approver), `criteria`, and two outgoing edges with `condition.outcome` = `approved` and `rejected` | red hexagon `APPROVAL GATE`, rejected path in red |

`trigger` ∈ `always` · `on_exception` · `low_confidence` · `sample`. Exceptions with handling `manual_review` or
`escalate` are drawn as **human queues** in the notified actor's lane.

`automation_hint` on tasks — a *hint* for MOTHER, not a decision:
`ai_candidate | deterministic_code | integration | human | unknown`.

## 5. Decision rules

`logic.kind` is one of:

- `table` — decision table: `columns` (input refs `ent_x.attr`), `rows` (`when` list aligned with columns,
  `then` outcome). Use `"*"` for any. Preferred: deterministic and testable.
- `expression` — a boolean/arith expression over input refs (CEL-compatible subset).
- `natural_language` — text only. Allowed in draft; **fails DoR** if the rule gates an edge.

`outcomes` must equal the set of `condition.outcome` values on the decision node's outgoing edges.

## 6. Acceptance criteria

Given/When/Then, each a list of plain sentences. `applies_to` lists node / rule / exception / SLA ids.
Rendered to Gherkin by M7. Rules:

- At least one `then` must be observable (a state change, output entity, notification or decision outcome).
- No vague terms from the glossary that are flagged `ambiguous: true` without a definition.

## 5a. Variants: as-is and to-be (v1.1)

An idea has up to two process models:

| `process.variant` | Meaning | Created by | Changes after |
|---|---|---|---|
| `as_is` | How the work is done today | M0 in as-is mode, or M1/M2 from documents | Frozen once confirmed and forked |
| `to_be` | The improved or new design. **Stories, DoR and exports are always for the to-be** | M0 in idea mode; or the M11 fork of a confirmed as-is | Patches, refinements |

`process.idea_id` links both to their idea. A forked to-be has `derived_from = {process_id, version}`.

Node fields for comparison:
- `as_is_effort = {minutes_per_case, pain_points[]}`: captured in the as-is (slot C17), copied to the to-be at the fork.
  Used to compute suggestion benefits and the "minutes today" column.
- `change = {kind, suggestion_id, was}` (to-be only): set when an accepted M11 suggestion changed the step.
  `kind` ∈ automated · automated_with_review · new · modified · control_added; `was` = the as-is `hitl.mode`.

## 6a. Goals, personas, NFRs, scope (v1.1)

- **Goal**: `statement` is an imperative verb phrase ("Cut the time it takes to complete KYC for a new client") so it composes into *"…, helping us cut the time it takes…"*. `metrics[]` = `{name, unit, baseline, target}`.
  `persona_ids` = who benefits.
- **Persona**: a beneficiary, optionally linked to the actor that represents them. `needs[]` in their words.
- **NFR**: `category` ∈ volume, performance, availability, security, privacy, audit, compliance, accessibility,
  retention, usability. `applies_to` = node ids, **empty = process-wide**. DoR requires `volume`, `security` and
  `audit` coverage for every story (configurable).
- **Scope**: `in[]`, `out[]`, `assumptions[]`, `constraints[]`, and `confirmed_none[]`. The last records coverage
  slots the requester explicitly said don't apply (`decisions`, `exceptions`, `systems`), so they're not asked again.

AC `kind` (v1.1): `happy_path` (default) · `edge_case` · `negative` · `nfr`. Stories that contain a decision, wait
or exception need at least one `edge_case`/`negative` AC (DOR-15).

## 7. Patch model

Envelope (`schemas/patch.schema.json`):

```json
{
  "patch_id": "uuid",
  "process_id": "proc_client_onboarding",
  "base_version": 3,
  "ops": [ RFC 6902 operations on the IR document ],
  "author": { "kind": "user|agent", "id": "agent:interviewer" },
  "reason": "Answer from MLRO to question q_...",
  "evidence": { "question_id": "...", "answer_id": "...", "source_ids": [] },
  "interpretation_confidence": 0.9,
  "auto_apply": false,
  "status": "proposed|accepted|rejected|applied|conflicted",
  "reviewed_by": null
}
```

Patch Service rules:

1. `ops` may not touch `/stories`, `/process/version` or `/process/updated_at` (derived / managed).
2. After apply, the resulting document **must** validate against the schema and pass referential integrity
   (every referenced id exists and is not `rejected`). Otherwise the patch is rejected with the validation errors.
3. Applying a patch whose evidence is an SME answer sets `meta.status=confirmed` and `meta.confirmed_by` on the
   touched elements (the interviewer includes these ops explicitly; the service validates them).
4. `auto_apply=true` is allowed for `author.kind=user` and for the first extraction draft. Agent patches after
   the first draft are `proposed` unless the auto-accept policy (M6 §6) allows otherwise.

## 8. Confidence model (deterministic — implemented in `packages/confidence_dor`)

### 8.1 Element confidence

Let `S+` be supporting provenance refs, `S−` contradicting refs. For each ref `s`:
`w(s)` = source authority weight, `c(s)` = extraction certainty capped at 0.9.

```
evidence  = 1 − Π_{s ∈ S+} (1 − w(s) · c(s))
conflict  = 0.5 if S− non-empty and status != confirmed else 1.0
confidence =
   0                         if status = rejected
   max(evidence, 0.95)       if status = confirmed
   round(evidence · conflict, 3)  otherwise
```

Default authority weights (configurable per process):

| Source kind | Weight |
|---|---|
| `interview_answer` (SME) | 0.9 |
| `sop` | 0.8 |
| `document` | 0.7 |
| `transcript` | 0.6 |
| `spreadsheet` | 0.6 |
| `email` | 0.5 |
| `recording` | 0.5 |
| `manual` (typed by BA) | 0.7 |
| `intake` (requester's own answers in M0) | 0.8 |
| `inferred` | 0.3 |

Example: two supporting refs (SOP c=0.85, transcript c=0.8) → `1 − (1−0.68)(1−0.48)` = `1 − 0.32·0.52` = **0.834**.

### 8.2 Story confidence

```
story_confidence = max(0, min(confidence of every element in the story's closure) − 0.1 × open_blocking_gaps − 0.03 × open_major_gaps)
```

Story closure = its nodes + their actor, rules, SLAs, exceptions, goals, ACs, and input/output entities.

Requester answers in M0 start at 0.8 × 0.9 = **0.72 (amber)** and become 0.95 when confirmed in Validate.
That's deliberate: a single person's description of their own idea is good evidence, but not confirmed until
they see it played back as a whole.

Bands: **green ≥ 0.80**, **amber 0.50–0.79**, **red < 0.50**.

## 9. Referential integrity checklist (enforced by `ir_core.validate`)

- `edge.from`/`edge.to` ∈ nodes
- `node.actor_id` ∈ actors; `node.inputs/outputs` ∈ entities; `node.rule_ids` ∈ decision_rules, etc.
- `provenance.source_id` ∈ sources ∪ {`src_inferred`}
- `ac.applies_to`, `sla.applies_to`, `exception.applies_to` ∈ known element ids
- `edge.condition.rule_id` ∈ decision_rules and `edge.condition.outcome` ∈ that rule's `outcomes`
- `exception.handling.target_node_id` ∈ nodes (when present)
- `node.goal_ids` ∈ goals; `node.system_ids` ∈ actors **of kind `system`**
- `goal.persona_ids` ∈ personas; `persona.actor_id` ∈ actors; `nfr.applies_to` ∈ nodes
- `story.*_ids` ∈ their collections
