---
name: improve_suggest
module: M11
output_model: SuggestionList
variables: [as_is_view, candidates, pain_points, effort, sme_answers, scope, cases_per_month, id_conventions]
temperature: 0
---
You are improving a business process that exists today. Suggest where AI agents, integrations or automated rules
would remove manual work, while keeping people in control where judgement or regulation requires it.

For each candidate (and any clear opportunity the candidates missed, flagged "source": "llm"), return:
- title (≤ 90 characters, starts with a verb, plain English)
- kind: automate_step | automate_with_review | add_human_queue | deterministic_rule | add_integration | remove_step | merge_steps | add_sla
- change_summary: what the to-be does differently, in 1–2 sentences
- rationale: why, in the requester's own terms (their pain points)
- evidence: 1–3 quotes copied VERBATIM from the pain points, answers or SME answers, each with its locator
- minutes_saved_per_case: from the effort data only; null if the step has no effort figure
- controls: the human control kept or added (review, queue, approval, sample). Say "None needed: <why>" if none
- risk: the main risk in one sentence
- confidence 0–1
- ops: JSON Patch operations on the to-be (a copy of the as-is) that implement the change. Set the node's hitl,
  system_ids and description, and add exceptions for failures that must reach a person.

Rules:
- Never suggest removing or automating a decision listed as out of scope or reserved for a named role
  (e.g. "stays with the MLRO"). List those under "not_suggested" with the reason.
- Every automated step that can fail must send failures to a person.
- Do not invent effort numbers, volumes, systems or APIs. Use only what the data says.
- Return {suggestions: [...], not_suggested: [{target, reason}]}.
<data>as-is: {{as_is_view}}
candidates: {{candidates}}
pain points: {{pain_points}}
effort (minutes per case): {{effort}}
SME answers: {{sme_answers}}
scope: {{scope}}
cases per month: {{cases_per_month}}</data>
<data>
id_conventions: {{ id_conventions }}
</data>
