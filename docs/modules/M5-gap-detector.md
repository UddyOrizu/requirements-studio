# M5 — Gap Detector

## Purpose
Continuously find what's missing, ambiguous, contradictory or weak in the IR — and express each as a precise,
answerable gap. **No question is ever asked without a gap behind it.**

## Triggers
`ir.patched` (debounced 30 s per process), manual "re-scan", nightly full scan.

## Detectors

### A. Structural (deterministic, `packages/gap_rules`) — run on every patch

| Gap type | Rule | Severity |
|---|---|---|
| `node_without_actor` | `task` with no `actor_id` | blocking |
| `decision_missing_branch` | decision rule `outcomes` not all covered by outgoing edges, or `table` rule inputs have unhandled value (enum entity attr not covered by rows and no `*` row) | blocking |
| `decision_missing_default` | decision with no `is_default` edge and rule not provably exhaustive | major |
| `wait_without_timeout` | `wait` node with no SLA and no exception with timeout trigger | blocking |
| `unreachable_node` | node not reachable from `start` | major |
| `no_path_to_end` | node from which no `end` is reachable | blocking |
| `undefined_entity_reference` | AC/rule references `ent_x.attr` not defined on the entity | major |
| `sla_without_breach_action` | SLA `breach_action.action == "undefined"` | major |
| `exception_without_handling` | exception `handling.action == "undefined"` | major |
| `node_without_acceptance_criteria` | task/decision with no AC applying to it | major |
| `natural_language_rule_gating_edge` | rule with `logic.kind=natural_language` referenced by an edge condition | major |
| `low_confidence_element` | `meta.confidence < 0.5` and not rejected | minor (major if on a decision/rule) |

### B. Conflict (deterministic)
- `conflicting_sources` — any element with ≥ 1 `contradicts` provenance and `status != confirmed`. Severity
  blocking if the field is `actor_id`, a rule, or an SLA duration; else major. The gap carries both excerpts.

### C. Semantic (LLM, `prompts/gaps_semantic.md`) — run when structural pass is clean for a region or on nightly scan
Input: a **subgraph view** (node + neighbours + rules + ACs + glossary) — not the whole IR — to keep prompts small.

| Gap type | Example |
|---|---|
| `ambiguous_term` | "escalate promptly", "significant adverse media" |
| `undefined_threshold` | "high-value client" with no amount |
| `implied_missing_step` | documents received → screening, but nobody checks documents are complete |
| `unclear_ownership_of_data` | who maintains the risk rating once assigned |
| `missing_exception_path` | external system call with no failure handling |

The LLM must return target element ids from the input view; any id not in the view is discarded.
Semantic gaps start at `severity=major` unless the model marks blocking **and** the target is a decision/rule/SLA.

### D. Coverage (deterministic) — document-led processes only
When a process has **no active intake session** (it came from documents), M5 evaluates the M0 coverage
checklist (`rs_reference.coverage`) and opens one `coverage_missing` gap per unfilled slot (`coverage_slot` set,
`target_refs` = the IR section, e.g. `/nfrs`). Severity: major, except C03 personas (minor). Routed to the
**process owner** by default (M6 §2). This is how the document path also gets discovery questions: goal, metric,
volume, NFRs, scope. In an active intake session, M0 drives coverage directly and these gaps are not raised.

### E. Story readiness (deterministic)
Raised from failing DoR checks so they become questions, merged per type into one gap with many targets:

| Gap type | From | Severity |
|---|---|---|
| `story_value_missing` | DOR-12 (no `goal_ids` on the story's task) | major |
| `story_priority_missing` | DOR-13 | major |
| `story_edge_cases_missing` | DOR-15 | major |
| `hitl_undefined` | DOR-16: task without `hitl.mode` (document-led: covered by the C16 coverage gap) | major |
| `approval_gate_incomplete` | DOR-16: approval without approver, criteria or a `rejected` path | blocking |

Intake-originated gaps (the requester said "not sure — ask someone") use `detector: intake`, and types such as
`integration_capability_unknown` or `unclear_business_rule`.

### Suppression rules (avoid duplicate noise)
- No `low_confidence_element` for an element that already has an open `conflicting_sources` gap (the conflict
  is the cause of the low score).
- No `decision_missing_default` while a `decision_missing_branch` gap is open on the same decision.
- A decision whose rule outcomes are all wired and that has an `is_default` edge never raises
  `decision_missing_default`.

## Gap object
See `schemas/gap.schema.json`. Each gap has `target_refs` (JSON pointer paths), `why_it_matters`, a drafted
`question` with `answer_type` and `suggested_answers`, routing hints (`topic_tags`, `candidate_actor_ids`), and
`priority`.

## Priority
```
severity_weight = {blocking: 10, major: 4, minor: 1}
downstream = number of nodes reachable from the target node (decision/wait gaps propagate)
stories_blocked = number of stories whose closure includes a target
priority = severity_weight × (1 + log2(1 + downstream)) × (1 + stories_blocked)
```

## Lifecycle
`open → asked → answered → resolved` (or `dismissed` / `waived` by owner with reason).
- **Auto-resolve:** after each `ir.patched`, re-run the check that produced the gap on its targets; if it passes,
  set `resolved` with `resolved_by_patch_id`.
- **Fingerprint** `sha1(type + ('#' + coverage_slot if any) + '|' + '|'.join(sorted(target_refs)))` prevents duplicate gaps across scans; a dismissed gap with the
  same fingerprint is not re-opened unless the targets change.

## Acceptance tests (fixtures: `samples/ir_client_onboarding.json` → `samples/gaps_client_onboarding.json`)
- **AC-M5-1** Structural + conflict detectors produce exactly the deterministic gaps in the sample gap file
  (`detector in [structural, conflict]`), matched by fingerprint.
- **AC-M5-2** `wait_without_timeout` on `node_wait_docs` is blocking with the question
  "What happens if the client hasn't sent their documents after N days?" style phrasing and `answer_type=duration`
  or `choice`.
- **AC-M5-3** Applying `samples/patch_example.json` auto-resolves the `conflicting_sources` gap on
  `node_high_risk_approval`.
- **AC-M5-4** Semantic detector output referencing an id outside its subgraph view is dropped.
