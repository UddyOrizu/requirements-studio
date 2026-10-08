# M7 — Story & Gherkin Renderer

## Purpose
Render the human view from the IR: user stories with acceptance criteria in Given/When/Then, and `.feature` files.
Rendering is **deterministic templating**; an optional LLM polish step improves wording only.

## Story derivation rules (deterministic)

1. One story per `task` node that is not `rejected`.
2. A `decision` node is folded into the story of its **preceding task** (the task that produces the decision's
   inputs); its rule and branch ACs become that story's ACs. If none, it gets its own story.
3. A `wait` node + its SLA/timeout exception is folded into the story of the task that initiated the wait.
4. Exceptions attach to the story of each node in `applies_to`.
5. `story_id = "story_" + node_id.removeprefix("node_")`. Stable across renders.

## Story fields (detailed story — schema `$defs/Story`, reference `rs_reference.derive_stories`)

| Field | Derivation |
|---|---|
| `title` | node `name` |
| `as_a` | node `actor_id` (rendered as name, with a/an) |
| `i_want` | node `description`, first letter lower-cased, trailing full stop removed (rendered "to …") |
| `so_that` | **value, not mechanics.** `"{outcome}, helping us {goal statements joined with 'and'}"`. If no goals: `outcome`. If no outcome: `"we can {goals}"`. Last resort: `"the next step can proceed"` (and DOR-12 fails). |
| `goal_ids` / `persona_ids` | goals on the story's nodes / personas on those goals (= *who benefits*) |
| `priority` | task node `priority` (MoSCoW) |
| `ac_ids` | live ACs whose `applies_to` intersects the story's node ids, each tagged by `kind` |
| `edge_cases` | exceptions in the closure (with handling in plain words) + ACs of kind `edge_case`/`negative` |
| `nfr_ids` | NFRs with empty `applies_to` (process-wide) or intersecting the story's nodes |
| `data_requirements` | per entity in node inputs/outputs: `read` / `write` / `read_write` + attribute names |
| `dependencies` | upstream/downstream stories (via edges and exception/SLA routes) + system actors (`system_ids`) |
| `open_questions` | open/asked/answered gaps targeting the closure, with who they're waiting on |
| `change` | to-be only: node `change` + as-is minutes, rendered as *Change from today* |
| `human_control` | task `hitl` (mode, reviewer/approver, trigger, criteria) + exceptions in the story that go to a person (`queues`) |
| `automation_hint` | from the task node, for MOTHER |
| `confidence`, `dor_status`, `open_gap_ids` | IR §8.2, M8 |

Fold rule tie-break: a decision/wait folds into its predecessor **task nearest the start along main-path edges**
(nodes reached only via exception/SLA routes come after). Stories are emitted in that same flow order.
If a decision/wait has no task predecessor, M5 raises `implied_missing_step` and the node is left out of
stories until fixed.

## Markdown template (detailed)

A process context header (goals with metrics, scope, NFRs, **what changes from today** table when an as-is exists, **human-in-the-loop and approval gates table**, story index with control column), then per story. The process flow diagram is the companion output (M10):

```markdown
### {title} · `{story_id}`
**{priority}** · Confidence **{band} ({confidence})** · DoR **{dor_status}** · Automation hint **{hint}** · Open questions **{n}**

> As {a/an} **{actor}**, I want **to {i_want}**, so that **{so_that}**.

**Who benefits:** {personas} · **Goals served:** {goal statements}
**Human in the loop:** {mode} — reviewer/approver, trigger, checks; exceptions handed to a person
**Acceptance criteria** — numbered, each with kind, Given/When/Then (And for extra lines)
**Edge cases & exceptions** — title (`ref`): handling
**Business rules** — decision tables rendered as tables; expressions as code; natural language flagged ⚠
**Time limits (SLAs)** — duration, calendar, clock start/stop, breach action
**Data** — | Entity | Access | Attributes |
**Non-functional** — [category] statement
**Dependencies:** upstream · downstream · systems
**Open questions** — text (severity, status, waiting on SME) `gap_id`
**Not ready because** — failing DoR checks with messages (only when not ready)
**Traceability:** nodes · sources (assumptions shown as "Studio assumption (confirmed by requester)")
```

Full examples: `samples/client_kyc/stories_client_kyc.md` (all ready) and `samples/stories_client_onboarding.md`
(document-led, mid-review, showing *Not ready because* sections).

## Gherkin
One `Feature` per process; one `Scenario` per AC (each AC once, tagged with every story that contains it); scenario tags `@{story_id} @{ac_id}` plus `@sla` / `@exception`
where relevant. Multiple Given/When/Then lines rendered with `And`. Example: `samples/features/client_onboarding.feature`.

## Polish (optional, `prompts/render_polish.md`)
Input: the templated story; output: same JSON shape with improved `i_want`/`so_that` wording. Guardrails: no new
facts — a validator checks that every noun phrase in the polished text appears in the IR closure (names,
entities, glossary) or in a stop-list; otherwise the template text is kept.

## Editing from the stories view
"Edit" on any field opens the underlying IR element (actor, node description, AC) in the side panel. No prose
editing of the rendered story.

## Acceptance tests
- **AC-M7-1** `derive_stories` on both sample IRs equals the stored `stories` exactly (validator check), and the
  markdown matches the sample files when polish is off.
- **AC-M7-5** Every client KYC (to-be) story's `so_that` contains its outcome and at least one goal statement; `story_screen`
  lists `gap_match_threshold` as an open question waiting on `sme_priya_shah`.
- **AC-M7-2** `node_risk_decision` folds into `story_risk_rate`; `node_wait_docs` folds into `story_request_docs`.
- **AC-M7-3** Gherkin output parses with `gherkin-official` and contains one scenario per AC.
- **AC-M7-4** Re-rendering an unchanged IR yields byte-identical markdown (polish off).
