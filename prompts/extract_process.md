---
name: extract_process
module: M2
output_model: ExtractionResult
variables: [process_name, known_actors, known_entities, blocks]
temperature: 0
---
Extract the business process described in the source blocks.

Return:
- actors: roles, teams, systems or external parties that perform or receive work
- entities: business objects/documents/data and their attributes when stated
- steps: each with type (task|decision|wait|event|start|end), name (verb-object, ≤ 6 words), description,
  performer (actor name), inputs, outputs, order_hint (integer), and for decisions the list of outcomes
- rules: any criteria, thresholds or tables that determine a decision
- exceptions: what can go wrong and what is done about it (handling may be "undefined" if not stated)
- slas: time limits, with ISO-8601 duration if stated
- terms: business terms; mark ambiguous=true for vague qualifiers ("promptly", "significant")

For EVERY item give: block_ids (citations), excerpt (verbatim ≤ 300 chars from one cited block),
extraction_certainty (0–1). Prefer names already in known_actors / known_entities when they refer to the same thing.

- For each step also give `control`: automated | hitl_review | human_task | approval | unknown, from the wording
  ("approved by", "signed off by", "reviews before" → approval / hitl_review; "the system", "automatically" → automated).
<data>{{process_name}} | known actors: {{known_actors}} | known entities: {{known_entities}}</data>
<source>{{blocks}}</source>
