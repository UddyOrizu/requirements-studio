---
name: intake_interpret
module: M0
output_model: IntakeInterpretation
variables: [target, answer, turn_id, source_id, ir_view, allowed_paths, id_conventions]
temperature: 0
---
Turn the requester's answer into JSON Patch operations on the process model.
- Model only what the answer states. For each new or changed element include a provenance ref with
  source_id "{{ source_id }}", locator {kind:"turn", value:"{{turn_id}}"}, and an excerpt that is copied VERBATIM
  from the answer (the shortest span that supports it).
- Anything you infer that is not stated (an implied step, a connecting edge, a definition) must use
  source_id "src_inferred" and be listed in "assumptions" in plain English.
- You may refine earlier elements when the answer makes them precise (e.g. turn a natural-language rule into an
  expression once the attribute it depends on exists).
- If the answer is partial or raises an obvious next question about the same topic, set follow_up_question
  (one sentence). Otherwise null.
- Return {ops, captured: [plain-English bullet per change], assumptions: [..], follow_up_question}.
- Human-in-the-loop answers (slot C16): set each task's `hitl` = {mode: automated | hitl_review | human_task | approval,
  actor_id (reviewer/approver), trigger (hitl_review), criteria}. An approval the requester describes as a separate check
  ("X must approve before…") becomes its own task with hitl.mode "approval" and two outgoing edges whose condition.outcome
  is "approved" and "rejected".
<data>target: {{target}}
answer: {{answer}}
model view: {{ir_view}}
allowed: {{allowed_paths}}</data>

{# Note: For turn 0 (`target.kind = "idea"`), extract a first goal, roles and candidate steps without edges unless the order is explicit. #}
<data>
id_conventions: {{ id_conventions }}
</data>
